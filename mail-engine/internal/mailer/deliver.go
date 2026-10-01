package mailer

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net/smtp"
)

func randToken(n int) string {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "0000000000000000"[:n*2]
	}
	return hex.EncodeToString(b)
}

// DeliveryResult reports what happened to a send.
type DeliveryResult struct {
	Delivered bool
	DryRun    bool
	Err       error
}

// Deliver relays a fully-built (and DKIM-signed) message via SMTP. When relayAddr
// is empty it is a no-op "dry run" (dev mode without an MTA) so the pipeline runs
// end to end and the signed message can be inspected/tested without a live relay.
//
// In production relayAddr points at the local Stalwart/Postfix submission port
// (e.g. "127.0.0.1:587" or ":25"), which handles MX lookup and outbound TLS.
func Deliver(relayAddr, envelopeFrom, recipient string, raw []byte) DeliveryResult {
	if relayAddr == "" {
		return DeliveryResult{Delivered: false, DryRun: true}
	}
	if err := smtp.SendMail(relayAddr, nil, envelopeFrom, []string{recipient}, raw); err != nil {
		return DeliveryResult{Delivered: false, Err: fmt.Errorf("relay %s: %w", relayAddr, err)}
	}
	return DeliveryResult{Delivered: true}
}
