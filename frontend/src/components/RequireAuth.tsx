/** Route guard for protected routes. */

import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/**
 * Render the nested route only while a valid session exists.
 *
 * Shows a brief loading state while the initial ``/auth/me`` check is in
 * flight, and redirects to the login page (remembering where the user was
 * headed) when no session is present.
 *
 * @return The guarded route element.
 */
export default function RequireAuth() {
  const { user, initializing } = useAuth()
  const location = useLocation()

  if (initializing) {
    return <div className="loading">Loading…</div>
  }
  if (!user) {
    // Remember where the user was headed so login can send them back.
    return (
      <Navigate to="/login" replace state={{ from: location.pathname }} />
    )
  }
  return <Outlet />
}
