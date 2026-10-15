import { createContext, useContext } from 'react'

export type Identity = { user: { id: number; email: string; name: string }; workspace_id: number; role: 'owner' | 'editor' | 'reviewer' | 'viewer'; csrf_token: string; workspaces: { id: number; name: string; role: string }[] }
export const Auth = createContext<Identity | null>(null)
export function useAuth() {
  const actor = useContext(Auth)
  if (!actor) throw new Error('This page requires a signed-in workspace')
  return actor
}
