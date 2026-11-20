/** Protected home page: session summary plus logout (module list lands in 5.2). */

import { useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

/**
 * Render the authenticated landing page.
 *
 * Shows who is signed in and offers logout, which revokes the session
 * server-side and returns to the login page. The module list (task 5.2)
 * will replace this placeholder content.
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
        <h1>Welcome, {user.username}</h1>
        <p className="muted">
          Your session is active. The module browser will appear here.
        </p>
      </main>
    </div>
  )
}
