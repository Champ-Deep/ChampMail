import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '../api/client';

interface OnboardingState {
  // Completed and skipped tours
  completedTours: string[];
  skippedTours: string[];

  // Current tour state
  currentTour: string | null;
  isRunning: boolean;
  stepIndex: number;

  // Actions
  startTour: (tourId: string) => void;
  stopTour: () => void;
  completeTour: (tourId: string) => void;
  skipTour: (tourId: string) => void;
  setStepIndex: (index: number) => void;
  resetTour: (tourId: string) => void;
  resetAllTours: () => void;

  // Check if a tour should auto-start
  shouldShowTour: (tourId: string) => boolean;

  // Sync with backend
  syncProgress: () => Promise<void>;
}

export const useOnboardingStore = create<OnboardingState>()(
  persist(
    (set, get) => ({
      completedTours: [],
      skippedTours: [],
      currentTour: null,
      isRunning: false,
      stepIndex: 0,

      startTour: (tourId: string) => {
        set({
          currentTour: tourId,
          isRunning: true,
          stepIndex: 0,
        });
      },

      stopTour: () => {
        set({
          currentTour: null,
          isRunning: false,
          stepIndex: 0,
        });
      },

      completeTour: (tourId: string) => {
        const { completedTours } = get();
        if (!completedTours.includes(tourId)) {
          set({
            completedTours: [...completedTours, tourId],
            currentTour: null,
            isRunning: false,
            stepIndex: 0,
          });

          // Sync with backend (fire and forget)
          api.post(`/auth/onboarding/${tourId}/complete`).catch(console.error);
        }
      },

      skipTour: (tourId: string) => {
        const { skippedTours } = get();
        if (!skippedTours.includes(tourId)) {
          set({
            skippedTours: [...skippedTours, tourId],
            currentTour: null,
            isRunning: false,
            stepIndex: 0,
          });

          // Sync with backend (fire and forget)
          api.post(`/auth/onboarding/${tourId}/skip`).catch(console.error);
        }
      },

      setStepIndex: (index: number) => {
        set({ stepIndex: index });
      },

      resetTour: (tourId: string) => {
        const { completedTours, skippedTours } = get();
        set({
          completedTours: completedTours.filter(id => id !== tourId),
          skippedTours: skippedTours.filter(id => id !== tourId),
        });
      },

      resetAllTours: () => {
        set({
          completedTours: [],
          skippedTours: [],
          currentTour: null,
          isRunning: false,
          stepIndex: 0,
        });
      },

      shouldShowTour: (tourId: string) => {
        const { completedTours, skippedTours, isRunning } = get();
        return (
          !completedTours.includes(tourId) &&
          !skippedTours.includes(tourId) &&
          !isRunning
        );
      },

      syncProgress: async () => {
        try {
          const response = await api.get('/auth/onboarding/progress');
          const { completed_tours, skipped_tours } = response.data;
          set({
            completedTours: completed_tours || [],
            skippedTours: skipped_tours || [],
          });
        } catch (error) {
          console.error('Failed to sync onboarding progress:', error);
        }
      },
    }),
    {
      name: 'champmail-onboarding',
      partialize: (state) => ({
        completedTours: state.completedTours,
        skippedTours: state.skippedTours,
      }),
    }
  )
);
