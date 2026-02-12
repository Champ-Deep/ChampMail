import { useCallback, useEffect } from 'react';
import Joyride, { type CallBackProps, STATUS, EVENTS, ACTIONS } from 'react-joyride';
import { useOnboardingStore } from '../../store/onboardingStore';
import { getTourById, TOUR_IDS } from './tours';

// Custom styles for the tour
const joyrideStyles = {
  options: {
    arrowColor: '#ffffff',
    backgroundColor: '#ffffff',
    beaconSize: 36,
    overlayColor: 'rgba(0, 0, 0, 0.5)',
    primaryColor: '#3b82f6',
    spotlightShadow: '0 0 15px rgba(0, 0, 0, 0.5)',
    textColor: '#334155',
    width: 380,
    zIndex: 1000,
  },
  buttonNext: {
    backgroundColor: '#3b82f6',
    borderRadius: '8px',
    color: '#ffffff',
    fontSize: '14px',
    padding: '8px 16px',
  },
  buttonBack: {
    color: '#64748b',
    fontSize: '14px',
    marginRight: '8px',
  },
  buttonSkip: {
    color: '#94a3b8',
    fontSize: '14px',
  },
  tooltip: {
    borderRadius: '12px',
    boxShadow: '0 10px 40px rgba(0, 0, 0, 0.15)',
    padding: '20px',
  },
  tooltipTitle: {
    color: '#1e293b',
    fontSize: '18px',
    fontWeight: 600,
    marginBottom: '8px',
  },
  tooltipContent: {
    color: '#475569',
    fontSize: '14px',
    lineHeight: '1.6',
  },
  spotlight: {
    borderRadius: '8px',
  },
};

interface OnboardingProviderProps {
  children: React.ReactNode;
}

export function OnboardingProvider({ children }: OnboardingProviderProps) {
  const {
    currentTour,
    isRunning,
    stepIndex,
    completeTour,
    skipTour,
    stopTour,
    setStepIndex,
    shouldShowTour,
    startTour,
  } = useOnboardingStore();

  // Get steps for the current tour
  const steps = currentTour ? getTourById(currentTour) : [];

  // Handle Joyride callback
  const handleCallback = useCallback(
    (data: CallBackProps) => {
      const { status, action, index, type } = data;

      // Handle tour completion
      if (status === STATUS.FINISHED) {
        if (currentTour) {
          completeTour(currentTour);
        }
        return;
      }

      // Handle tour skip
      if (status === STATUS.SKIPPED) {
        if (currentTour) {
          skipTour(currentTour);
        }
        return;
      }

      // Handle step navigation
      if (type === EVENTS.STEP_AFTER || type === EVENTS.TARGET_NOT_FOUND) {
        if (action === ACTIONS.NEXT) {
          setStepIndex(index + 1);
        } else if (action === ACTIONS.PREV) {
          setStepIndex(index - 1);
        }
      }

      // Handle close button
      if (action === ACTIONS.CLOSE) {
        stopTour();
      }
    },
    [currentTour, completeTour, skipTour, stopTour, setStepIndex]
  );

  // Auto-start welcome tour for new users
  useEffect(() => {
    // Small delay to let the page render
    const timer = setTimeout(() => {
      if (shouldShowTour(TOUR_IDS.WELCOME)) {
        startTour(TOUR_IDS.WELCOME);
      }
    }, 1000);

    return () => clearTimeout(timer);
  }, [shouldShowTour, startTour]);

  return (
    <>
      {children}
      <Joyride
        steps={steps}
        run={isRunning}
        stepIndex={stepIndex}
        callback={handleCallback}
        continuous
        showProgress
        showSkipButton
        hideCloseButton={false}
        disableOverlayClose
        disableScrolling={false}
        spotlightClicks={false}
        styles={joyrideStyles}
        locale={{
          back: 'Back',
          close: 'Close',
          last: 'Done',
          next: 'Next',
          skip: 'Skip tour',
        }}
      />
    </>
  );
}

export default OnboardingProvider;
