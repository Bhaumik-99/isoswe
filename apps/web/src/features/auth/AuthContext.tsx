import React, { createContext, useContext, useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import { FlatMembership, MeResponse, RoleType, UserProfile } from '../../types';

interface AuthContextType {
  user: UserProfile | null;
  roles: RoleType[];
  memberships: FlatMembership[];
  selectedFlat: FlatMembership | null;
  setSelectedFlat: (flat: FlatMembership | null) => void;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [roles, setRoles] = useState<RoleType[]>([]);
  const [memberships, setMemberships] = useState<FlatMembership[]>([]);
  const [selectedFlat, setSelectedFlat] = useState<FlatMembership | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchProfile = async (): Promise<void> => {
    try {
      const data = await apiClient.get<MeResponse>('/api/v1/me');
      setUser(data.user);
      setRoles(data.roles.map((r) => r.role));
      setMemberships(data.memberships);

      // Auto-select primary or first flat
      if (data.memberships.length > 0) {
        const primary = data.memberships.find((m) => m.is_primary) || data.memberships[0];
        setSelectedFlat(primary);
      }
    } catch {
      // Clear token if invalid
      apiClient.setToken(null);
      setUser(null);
      setRoles([]);
      setMemberships([]);
      setSelectedFlat(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    const existingToken = apiClient.getToken();
    if (existingToken) {
      fetchProfile();
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (token: string): Promise<void> => {
    setIsLoading(true);
    apiClient.setToken(token);
    await fetchProfile();
  };

  const logout = () => {
    apiClient.setToken(null);
    setUser(null);
    setRoles([]);
    setMemberships([]);
    setSelectedFlat(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        roles,
        memberships,
        selectedFlat,
        setSelectedFlat,
        isAuthenticated: !!user,
        isLoading,
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
