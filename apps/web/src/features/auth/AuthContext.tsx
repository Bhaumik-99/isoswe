import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import { sessionManager } from '../../services/sessionManager';
import { supabaseAuth } from '../../services/supabaseAuth';
import { FlatMembership, MeResponse, PermissionType, RoleType, UserProfile } from '../../types';

interface AuthContextType {
  user: UserProfile | null;
  roles: RoleType[];
  permissions: PermissionType[];
  memberships: FlatMembership[];
  selectedFlat: FlatMembership | null;
  setSelectedFlat: (flat: FlatMembership | null) => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  isSessionExpired: boolean;
  clearSessionExpired: () => void;
  login: (token: string, expiresInSeconds?: number) => Promise<RoleType[]>;
  logout: () => void | Promise<void>;
  refreshProfile: () => Promise<RoleType[]>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [roles, setRoles] = useState<RoleType[]>([]);
  const [permissions, setPermissions] = useState<PermissionType[]>([]);
  const [memberships, setMemberships] = useState<FlatMembership[]>([]);
  const [selectedFlat, setSelectedFlat] = useState<FlatMembership | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSessionExpired, setIsSessionExpired] = useState<boolean>(false);

  const fetchProfile = async (): Promise<RoleType[]> => {
    try {
      const data = await apiClient.get<MeResponse>('/api/v1/me');
      setUser(data.user);
      const userRoles = data.roles.map((r) => r.role);
      setRoles(userRoles);
      setPermissions(data.permissions ?? []);
      setMemberships(data.memberships);

      // Auto-select primary or first flat
      if (data.memberships.length > 0) {
        const primary = data.memberships.find((m) => m.is_primary) || data.memberships[0];
        setSelectedFlat(primary);
      }
      setIsSessionExpired(false);
      return userRoles;
    } catch {
      // Clear session if profile fetch fails
      apiClient.setToken(null);
      setUser(null);
      setRoles([]);
      setPermissions([]);
      setMemberships([]);
      setSelectedFlat(null);
      return [];
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // 1. Listen for session expiry from sessionManager or 401s
    const unsubscribeSession = sessionManager.onSessionExpired(() => {
      setUser(null);
      setRoles([]);
      setPermissions([]);
      setMemberships([]);
      setSelectedFlat(null);
      setIsSessionExpired(true);
    });

    // 2. Listen for Supabase session refresh and sign-out events
    const unsubscribeSupabase = supabaseAuth.onAuthStateChange((event, session) => {
      if (event === 'TOKEN_REFRESHED' && session?.access_token) {
        apiClient.setToken(session.access_token, session.expires_in);
      } else if (event === 'SIGNED_OUT') {
        apiClient.setToken(null);
        setUser(null);
        setRoles([]);
        setPermissions([]);
        setMemberships([]);
        setSelectedFlat(null);
      }
    });

    // 3. Hydrate session on initial mount
    const initSession = async () => {
      const existingToken = apiClient.getToken();
      if (existingToken) {
        await fetchProfile();
      } else {
        // Try hydrating from Supabase client session if available
        try {
          const session = await supabaseAuth.getSession();
          if (session?.accessToken) {
            apiClient.setToken(session.accessToken, session.expiresIn);
            await fetchProfile();
            return;
          }
        } catch {
          // Ignore
        }
        setIsLoading(false);
      }
    };

    initSession();

    return () => {
      unsubscribeSession();
      if (unsubscribeSupabase) {
        unsubscribeSupabase();
      }
    };
  }, []);

  const login = async (token: string, expiresInSeconds?: number): Promise<RoleType[]> => {
    setIsLoading(true);
    setIsSessionExpired(false);
    apiClient.setToken(token, expiresInSeconds);
    return await fetchProfile();
  };

  const logout = async (): Promise<void> => {
    try {
      await supabaseAuth.signOut();
    } catch {
      // Ignore network errors on logout
    }
    apiClient.setToken(null);
    setUser(null);
    setRoles([]);
    setPermissions([]);
    setMemberships([]);
    setSelectedFlat(null);
    setIsSessionExpired(false);
  };

  const clearSessionExpired = () => {
    setIsSessionExpired(false);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        roles,
        permissions,
        memberships,
        selectedFlat,
        setSelectedFlat,
        isAuthenticated: !!user,
        isLoading,
        isSessionExpired,
        clearSessionExpired,
        login,
        logout,
        refreshProfile: fetchProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
