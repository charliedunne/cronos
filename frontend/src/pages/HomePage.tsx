/** Protected home page: module list plus session header with logout. */

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import ModuleList from '../components/ModuleList'

/**
 * Render the authenticated landing page.
 *
 * Shows the signed-in user in the header, offers logout (which revokes the
 * session server-side and returns to the login page), and hosts the module
 * list as the main content.
 *
 * @return The home page element.
 */
export default function HomePage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  /**
   * Log out and return to the login page.
   */
  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  if (!user) {
    // The route guard normally prevents this; render nothing defensively.
    return null
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="brand">Cronos</span>
        <span className="spacer" />
        <span className="muted">
          {user.username}
          {user.is_admin ? ' (admin)' : ''}
        </span>
        <button type="button" onClick={handleLogout}>
          Log out
        </button>
      </header>

      <main className="content">
        <ModuleList />
      </main>
    </div>
  )
}
