import { ApiError, NO_SIGNAL_MESSAGE } from './api';

/**
 * Sign-in, sign-up and password errors in plain words. The sign-in library's
 * own messages ("Invalid login credentials", its network failure text) were
 * shown as they came. Matched on the library's error codes (auth-js
 * error-codes), falling back to its words for older errors without one.
 */
export function friendlyAuthError(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return e.message;   // our own API: already plain
  const err = (e ?? {}) as { name?: string; code?: string; message?: string; status?: number };
  const message = err.message ?? '';
  if (err.name === 'AuthRetryableFetchError' || err.status === 0
      || /network request failed|failed to fetch|network/i.test(message)) {
    return NO_SIGNAL_MESSAGE;
  }
  switch (err.code) {
    case 'invalid_credentials': return 'Wrong email or password.';
    case 'email_not_confirmed': return 'Confirm your email first — open the link we sent you.';
    case 'user_already_exists':
    case 'email_exists': return 'An account with this email already exists — sign in instead.';
    case 'email_address_invalid': return 'That email address does not look right.';
    case 'weak_password': return 'Choose a stronger password — at least 8 characters.';
    case 'same_password': return 'Choose a password different from your old one.';
    case 'over_email_send_rate_limit':
    case 'over_request_rate_limit': return 'Too many tries — wait a few minutes and try again.';
    case 'otp_expired': return 'This link has expired — ask for a new one.';
    case 'session_expired':
    case 'refresh_token_not_found': return 'Your sign-in has run out — sign in again.';
    case 'signup_disabled': return 'New accounts cannot be made right now.';
  }
  if (/invalid login credentials/i.test(message)) return 'Wrong email or password.';
  if (/email not confirmed/i.test(message)) return 'Confirm your email first — open the link we sent you.';
  if (/already registered/i.test(message)) return 'An account with this email already exists — sign in instead.';
  return message || fallback;
}
