import { useEffect, useRef, useCallback } from 'react';
import {
  getSavedSessions,
  updateSessionProgress,
  updateCertificationProgress,
} from '../services/storage';
import { api } from '../services/api';

interface NotificationState {
  sessionId: string;
  lastNotifiedStatus: string | null;
  lastNotifiedAction: string | null;
}

export function useNotifications() {
  const notificationStates = useRef<Map<string, NotificationState>>(new Map());

  // Show an alert popup
  const showNotification = useCallback((title: string, body: string, _sessionId: string) => {
    console.log('Showing alert:', title, body);
    alert(`${title}\n\n${body}`);
  }, []);

  // Check sessions and show notifications if action required
  const checkSessions = useCallback(async () => {
    const sessions = getSavedSessions();
    console.log('Checking', sessions.length, 'sessions for notifications');

    for (const session of sessions) {
      // Skip cancelled/closed polls
      if (['cancelled', 'closed', 'results'].includes(session.pollStatus)) {
        continue;
      }

      try {
        // Fetch current poll status
        const pollInfo = await api.getPoll(session.sessionId);
        console.log('Poll', session.sessionId.substring(0, 8), 'status:', pollInfo.status);

        // Update localStorage with fresh poll status if it changed
        if (pollInfo.status && pollInfo.status !== session.pollStatus) {
          console.log('Updating stored poll status:', session.pollStatus, '->', pollInfo.status);
          updateSessionProgress(session.sessionId, session.currentStep, pollInfo.status);
        }

        // Get or create notification state for this session
        let state = notificationStates.current.get(session.sessionId);
        if (!state) {
          state = {
            sessionId: session.sessionId,
            lastNotifiedStatus: session.pollStatus, // Initialize with saved status
            lastNotifiedAction: null,
          };
          notificationStates.current.set(session.sessionId, state);
        }

        // Check if certification phase started and we haven't notified for PPE
        if (pollInfo.status === 'certification') {
          try {
            const certStatus = await api.checkNodeCertification(session.sessionId, session.nodeId);
            console.log('Cert status:', certStatus.verified_edges, '/', certStatus.total_edges);

            // Update certification progress in localStorage
            updateCertificationProgress(
              session.sessionId,
              certStatus.verified_edges,
              certStatus.total_edges
            );

            // Only notify if there are pending PPEs and we haven't notified yet
            if (certStatus.verified_edges < certStatus.total_edges && state.lastNotifiedAction !== 'ppe') {
              showNotification(
                'PPE Required!',
                `Poll ${session.sessionId.substring(0, 8)}... needs PPE certification (${certStatus.verified_edges}/${certStatus.total_edges} done)`,
                session.sessionId
              );
              state.lastNotifiedAction = 'ppe';
            } else if (certStatus.verified_edges >= certStatus.total_edges) {
              // PPEs complete - clear the notification state so we don't notify again
              console.log('All PPEs complete, clearing notification state');
              state.lastNotifiedAction = null;
            }
          } catch (error) {
            console.log('Could not get cert status, checking saved session data');
            // Check if we have saved progress info
            if (session.verifiedEdges !== undefined && session.totalEdges !== undefined) {
              if (session.verifiedEdges < session.totalEdges && state.lastNotifiedAction !== 'ppe') {
                showNotification(
                  'PPE Required!',
                  `Poll ${session.sessionId.substring(0, 8)}... needs PPE certification (${session.verifiedEdges}/${session.totalEdges} done)`,
                  session.sessionId
                );
                state.lastNotifiedAction = 'ppe';
              }
            } else if (state.lastNotifiedStatus !== 'certification') {
              // If we can't get cert status and no saved data, still notify
              showNotification(
                'PPE Required!',
                `Poll ${session.sessionId.substring(0, 8)}... has entered certification phase!`,
                session.sessionId
              );
              state.lastNotifiedStatus = 'certification';
            }
          }
        }

        // Check if voting phase started and we haven't voted
        if (pollInfo.status === 'voting' && !session.hasVoted && state.lastNotifiedAction !== 'vote') {
          try {
            const certStatus = await api.checkNodeCertification(session.sessionId, session.nodeId);

            // Only notify if user is certified to vote
            if (certStatus.is_certified) {
              showNotification(
                'Vote Now!',
                `Poll ${session.sessionId.substring(0, 8)}... is ready for voting!`,
                session.sessionId
              );
              state.lastNotifiedAction = 'vote';
            }
          } catch (error) {
            console.error('Failed to check certification status:', error);
          }
        }

      } catch (error) {
        // Poll might not exist anymore, skip it
        console.debug('Failed to check session:', session.sessionId, error);
      }
    }
  }, [showNotification]);

  // Check once when the hook mounts (user enters the page)
  useEffect(() => {
    checkSessions();
  }, [checkSessions]);

  return { checkSessions };
}
