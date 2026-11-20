/** Shared header for authenticated pages: brand, optional back link, user, logout. */

import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

interface AppHeaderProps {
  /** Optional back link shown after the brand (e.g. "← Modules"). */
  back?: { label: string; to: string }
}

/**
 * Render the application header for authenticated pages.
 *
 * Shows the product name, an optional back link, a "Users" link for
 * administrators, the signed-in user, and a logout button that revokes the
 * session server-side and returns to login.
 *
 * @param props Optional back link configuration.
 * @return The header element.
 */
export default function AppHeader({ back }: AppHeaderProps) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  /**
   * Log out and return to the login page.
   */
  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <header className="app-header">
      <span className="brand">Cronos</span>
      {back !== undefined && (
        <Link to={back.to} className="back-link">
          {back.label}
        </Link>
      )}
      {user?.is_admin && (
        <Link to="/users" className="back-link">
          Users
        </Link>
      )}
      <span className="spacer" />
      <span className="muted">
        {user?.username}
        {user?.is_admin ? ' (admin)' : ''}
      </span>
      <button type="button" onClick={handleLogout}>
        Log out
      </button>
    </header>
  )
}
