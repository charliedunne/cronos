/** Route guard for administrator-only routes. */

import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/**
 * Render the nested route only while a signed-in user is an administrator.
 *
 * Must be nested inside ``RequireAuth`` (the page is unreachable without a
 * session). Non-administrators are sent back to the home page.
 *
 * @return The guarded route element, or a redirect for non-admins.
 */
export default function RequireAdmin() {
  const { user } = useAuth()

  if (!user?.is_admin) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}
