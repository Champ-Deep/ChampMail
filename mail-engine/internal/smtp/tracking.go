package smtp

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

type TrackingInjector struct {
	BaseURL   string
	MessageID string
	Domain    string
}

func NewTrackingInjector(baseURL, messageID, domain string) *TrackingInjector {
	return &TrackingInjector{
		BaseURL:   baseURL,
		MessageID: messageID,
		Domain:    domain,
	}
}

func (t *TrackingInjector) InjectPixel(htmlBody string) string {
	trackingURL := t.GetOpenTrackingURL()

	pixel := fmt.Sprintf(`<img src="%s" width="1" height="1" alt="" style="display:block;border:0;outline:none;text-decoration:none;" />`, trackingURL)

	if strings.Contains(htmlBody, "</body>") {
		htmlBody = strings.Replace(htmlBody, "</body>", pixel+"</body>", 1)
	} else {
		htmlBody += pixel
	}

	return htmlBody
}

func (t *TrackingInjector) WrapLinks(htmlBody string) string {
	linkPattern := regexp.MustCompile(`<a\s+([^>]*)href=["']([^"']+)["']([^>]*)>`)

	modified := linkPattern.ReplaceAllStringFunc(htmlBody, func(match string) string {
		parts := linkPattern.FindStringSubmatch(match)
		if len(parts) < 4 {
			return match
		}

		before := parts[1]
		originalURL := parts[2]
		after := parts[3]

		if strings.HasPrefix(originalURL, "mailto:") ||
			strings.HasPrefix(originalURL, "tel:") ||
			strings.HasPrefix(originalURL, "javascript:") {
			return match
		}

		trackingURL := t.GetClickTrackingURL(originalURL)

		return fmt.Sprintf("<a %shref=\"%s\"%s>", before, trackingURL, after)
	})

	return modified
}

func (t *TrackingInjector) InjectUTMParams(htmlBody string, utmSource, utmMedium, utmCampaign string) string {
	if utmSource == "" && utmMedium == "" && utmCampaign == "" {
		return htmlBody
	}

	linkPattern := regexp.MustCompile(`<a\s+([^>]*)href=["']([^"']+\?[^"']+)["']([^>]*)>`)

	modified := linkPattern.ReplaceAllStringFunc(htmlBody, func(match string) string {
		parts := linkPattern.FindStringSubmatch(match)
		if len(parts) < 4 {
			return match
		}

		before := parts[1]
		originalURL := parts[2]
		after := parts[3]

		parsed, err := url.Parse(originalURL)
		if err != nil {
			return match
		}

		query := parsed.Query()
		if utmSource != "" {
			query.Set("utm_source", utmSource)
		}
		if utmMedium != "" {
			query.Set("utm_medium", utmMedium)
		}
		if utmCampaign != "" {
			query.Set("utm_campaign", utmCampaign)
		}

		parsed.RawQuery = query.Encode()

		return fmt.Sprintf("<a %shref=\"%s\"%s>", before, parsed.String(), after)
	})

	return modified
}

func (t *TrackingInjector) GetOpenTrackingURL() string {
	if t.BaseURL == "" {
		t.BaseURL = "https://track.champmail.com"
	}
	return fmt.Sprintf("%s/track/open/%s", t.BaseURL, t.MessageID)
}

func (t *TrackingInjector) GetClickTrackingURL(originalURL string) string {
	if t.BaseURL == "" {
		t.BaseURL = "https://track.champmail.com"
	}

	encodedURL := url.QueryEscape(originalURL)
	return fmt.Sprintf("%s/track/click/%s?url=%s", t.BaseURL, t.MessageID, encodedURL)
}

func InjectTracking(htmlBody, messageID, baseURL, domain string, trackOpens, trackClicks bool) string {
	if htmlBody == "" {
		return htmlBody
	}

	injector := NewTrackingInjector(baseURL, messageID, domain)

	if trackClicks {
		htmlBody = injector.WrapLinks(htmlBody)
	}

	if trackOpens {
		htmlBody = injector.InjectPixel(htmlBody)
	}

	return htmlBody
}

func InjectUTM(htmlBody, utmSource, utmMedium, utmCampaign string) string {
	if htmlBody == "" {
		return htmlBody
	}

	injector := &TrackingInjector{}
	return injector.InjectUTMParams(htmlBody, utmSource, utmCampaign, utmMedium)
}

func ExtractLinks(htmlBody string) []string {
	linkPattern := regexp.MustCompile(`href=["']([^"']+)["']`)
	matches := linkPattern.FindAllStringSubmatch(htmlBody, -1)

	links := make([]string, 0, len(matches))
	seen := make(map[string]bool)

	for _, match := range matches {
		if len(match) < 2 {
			continue
		}
		link := match[1]
		if strings.HasPrefix(link, "mailto:") ||
			strings.HasPrefix(link, "tel:") ||
			strings.HasPrefix(link, "javascript:") {
			continue
		}
		if !seen[link] {
			seen[link] = true
			links = append(links, link)
		}
	}

	return links
}
