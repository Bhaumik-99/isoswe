/**
 * Genuine AWS Cognito Authentication Adapter
 *
 * Provides genuine authentication flows against AWS Cognito User Pool:
 * 1. Passwordless OTP initiation via Custom Authentication flow (CUSTOM_AUTH).
 * 2. OTP verification via RespondToAuthChallenge (CUSTOM_CHALLENGE).
 * 3. Enforces real token delivery; never accepts fabricated token strings.
 * 4. Fails closed when required Cognito configuration is missing in non-development environments.
 */

export interface CognitoTokens {
  idToken: string;
  accessToken: string;
  refreshToken?: string;
  expiresIn: number;
}

export interface InitiateAuthResult {
  session: string;
  challengeName: string;
  parameters?: Record<string, string>;
}

export class CognitoAuthError extends Error {
  code: string;

  constructor(message: string, code: string = 'COGNITO_ERROR') {
    super(message);
    this.name = 'CognitoAuthError';
    this.code = code;
  }
}

export class CognitoAuthAdapter {
  private userPoolId: string;
  private clientId: string;
  private region: string;
  private endpoint: string;

  constructor() {
    this.userPoolId = import.meta.env.VITE_COGNITO_USER_POOL_ID || '';
    this.clientId = import.meta.env.VITE_COGNITO_CLIENT_ID || '';
    this.region = import.meta.env.VITE_AWS_REGION || 'ap-south-1';
    this.endpoint = `https://cognito-idp.${this.region}.amazonaws.com/`;
  }

  isConfigured(): boolean {
    return Boolean(this.userPoolId && this.clientId);
  }

  private async callCognito<T>(target: string, payload: Record<string, unknown>): Promise<T> {
    if (!this.isConfigured()) {
      if (import.meta.env.DEV) {
        throw new CognitoAuthError(
          'AWS Cognito client configuration (VITE_COGNITO_CLIENT_ID) is not set. For local testing without AWS, please use the "Local Dev Personas" tab with seeded test accounts.',
          'COGNITO_NOT_CONFIGURED_DEV'
        );
      }
      throw new CognitoAuthError(
        'Authentication service is temporarily unavailable. Missing identity provider configuration.',
        'IDENTITY_PROVIDER_UNAVAILABLE'
      );
    }

    try {
      const response = await fetch(this.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-amz-json-1.1',
          'X-Amz-Target': `AWSCognitoIdentityProviderService.${target}`,
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorCode = data?.__type || data?.code || 'AUTH_FAILURE';
        const message = data?.message || `Cognito request failed: ${response.statusText}`;
        throw new CognitoAuthError(message, errorCode);
      }

      return data as T;
    } catch (err: unknown) {
      if (err instanceof CognitoAuthError) {
        throw err;
      }
      throw new CognitoAuthError(
        err instanceof Error ? err.message : 'Network error communicating with authentication service',
        'NETWORK_ERROR'
      );
    }
  }

  /**
   * Dispatches OTP challenge initiation to AWS Cognito for the given phone number or email.
   */
  async requestOtp(username: string): Promise<InitiateAuthResult> {
    const cleanUsername = username.trim();
    if (!cleanUsername) {
      throw new CognitoAuthError('Please provide a valid email or phone number', 'INVALID_INPUT');
    }

    interface CognitoInitiateResponse {
      Session?: string;
      ChallengeName?: string;
      ChallengeParameters?: Record<string, string>;
    }

    const result = await this.callCognito<CognitoInitiateResponse>('InitiateAuth', {
      AuthFlow: 'CUSTOM_AUTH',
      ClientId: this.clientId,
      AuthParameters: {
        USERNAME: cleanUsername,
      },
    });

    if (!result.Session) {
      throw new CognitoAuthError(
        'Failed to establish authentication challenge session with Cognito',
        'CHALLENGE_SESSION_MISSING'
      );
    }

    return {
      session: result.Session,
      challengeName: result.ChallengeName || 'CUSTOM_CHALLENGE',
      parameters: result.ChallengeParameters,
    };
  }

  /**
   * Submits the user-entered 6-digit OTP code to complete authentication and retrieve signed JWTs.
   */
  async verifyOtp(username: string, session: string, otpCode: string): Promise<CognitoTokens> {
    const cleanOtp = otpCode.trim();
    if (!cleanOtp || cleanOtp.length < 4) {
      throw new CognitoAuthError('Please enter a valid OTP verification code', 'INVALID_OTP');
    }

    interface CognitoChallengeResponse {
      AuthenticationResult?: {
        IdToken: string;
        AccessToken: string;
        RefreshToken?: string;
        ExpiresIn: number;
      };
      ChallengeName?: string;
    }

    const result = await this.callCognito<CognitoChallengeResponse>('RespondToAuthChallenge', {
      ChallengeName: 'CUSTOM_CHALLENGE',
      ClientId: this.clientId,
      Session: session,
      ChallengeResponses: {
        USERNAME: username.trim(),
        ANSWER: cleanOtp,
      },
    });

    if (!result.AuthenticationResult?.IdToken) {
      throw new CognitoAuthError(
        'Invalid or expired verification code. Please request a new code.',
        'INVALID_CHALLENGE_RESPONSE'
      );
    }

    return {
      idToken: result.AuthenticationResult.IdToken,
      accessToken: result.AuthenticationResult.AccessToken,
      refreshToken: result.AuthenticationResult.RefreshToken,
      expiresIn: result.AuthenticationResult.ExpiresIn || 3600,
    };
  }
}

export const cognitoAuth = new CognitoAuthAdapter();
