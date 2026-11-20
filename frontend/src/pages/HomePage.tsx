/** Protected home page: module list plus session header with logout. */

import { useAuth } from '../auth/AuthContext'
import AppHeader from '../components/AppHeader'
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
  const { user } = useAuth()

  if (!user) {
    // The route guard normally prevents this; render nothing defensively.
    return null
  }

  return (
    <div className="app-shell">
      <AppHeader />
      <main className="content">
        <ModuleList />
      </main>
    </div>
  )
}
