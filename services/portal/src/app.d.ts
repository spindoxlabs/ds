import type { DefaultSession } from '@auth/core/types';

declare global {
	namespace App {
		interface PageData {
			session?: (DefaultSession & { accessToken?: string }) | null;
		}
	}

	interface Window {
		__ENV?: {
			PUBLIC_KEYCLOAK_CLIENT_ID?: string;
		};
	}
}

declare module '@auth/core/types' {
	interface Session {
		accessToken?: string;
		userDid?: string | null;
		/**
		 * Every VC role the user holds. A person legitimately holds more than one
		 * — the same human is a data subject about their own consumption and a
		 * consumer user acting for an organisation — so role checks must ask
		 * "does this include", never "does this equal".
		 */
		userVcRoles?: string[];
		/** VC-JWS per role, so a call presents the credential it actually needs. */
		userVcJwsByRole?: Record<string, string>;
		/** The newest credential. Convenience only — prefer selecting by role. */
		userVcRole?: string | null;
		userVcJws?: string | null;
		userSubjectId?: string | null;
		error?: string;
	}
}

export {};
