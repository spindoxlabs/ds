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
		userVcRole?: string | null;
		userVcJws?: string | null;
		userSubjectId?: string | null;
		error?: string;
	}
}

export {};
