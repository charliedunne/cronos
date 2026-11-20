/** Application routes: public login page plus the protected area. */

import { Navigate, Route, Routes } from 'react-router-dom'
import RequireAuth from './components/RequireAuth'
import HomePage from './pages/HomePage'
import LoginPage from './pages/LoginPage'
import ModuleDetailPage from './pages/ModuleDetailPage'
import './App.css'

/**
 * Render the route table for the single-page app.
 *
 * @return The routed application element.
 */
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/modules/:id" element={<ModuleDetailPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
