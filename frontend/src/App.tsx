import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppShell } from './components/AppShell'
import { AuthPage } from './pages/AuthPage'
import { WorkspacePage } from './pages/WorkspacePage'
import { DashboardPage } from './pages/DashboardPage'
import './App.css'
import { AppDataProvider } from './data/AppDataContext'

function App() {
  return (
    <AppDataProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<AuthPage mode="login" />} />
          <Route path="/register" element={<AuthPage mode="register" />} />
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="assignments" element={<WorkspacePage page="assignments" />} />
            <Route path="calendar" element={<WorkspacePage page="calendar" />} />
            <Route path="subjects" element={<WorkspacePage page="subjects" />} />
            <Route path="assistant" element={<WorkspacePage page="assistant" />} />
            <Route path="integrations" element={<WorkspacePage page="integrations" />} />
            <Route path="settings" element={<WorkspacePage page="settings" />} />
            <Route path="timetable" element={<WorkspacePage page="timetable" />} />
            <Route path="*" element={<WorkspacePage page="not-found" />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppDataProvider>
  )
}

export default App
