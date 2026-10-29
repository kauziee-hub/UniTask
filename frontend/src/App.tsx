import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Spinner } from './components/ui'
import { AuthProvider, useAuth } from './lib/auth'
import { AuthPage } from './pages/AuthPage'
import { ClassesPage } from './pages/student/ClassesPage'
import { ConnectionsPage } from './pages/student/ConnectionsPage'
import { StudentCoursePage } from './pages/student/StudentCoursePage'
import { TodayPage } from './pages/student/TodayPage'
import { WorkDetailPage } from './pages/student/WorkDetailPage'
import { WorkPage } from './pages/student/WorkPage'
import { CourseworkReviewPage } from './pages/teacher/CourseworkReviewPage'
import { TeacherCoursePage } from './pages/teacher/TeacherCoursePage'
import { TeacherHome } from './pages/teacher/TeacherHome'

function Routed() {
  const { user, loading } = useAuth()
  if (loading) {
    return (
      <div style={{ padding: 48 }}>
        <Spinner />
      </div>
    )
  }
  if (!user) {
    return (
      <Routes>
        <Route path="/register" element={<AuthPage mode="register" />} />
        <Route path="*" element={<AuthPage mode="login" />} />
      </Routes>
    )
  }
  return (
    <Routes>
      <Route element={<Shell />}>
        {user.role === 'student' ? (
          <>
            <Route index element={<TodayPage />} />
            <Route path="work" element={<WorkPage />} />
            <Route path="work/:id" element={<WorkDetailPage />} />
            <Route path="classes" element={<ClassesPage />} />
            <Route path="classes/:id" element={<StudentCoursePage />} />
            <Route path="connections" element={<ConnectionsPage />} />
          </>
        ) : (
          <>
            <Route index element={<TeacherHome />} />
            <Route path="classes/:id" element={<TeacherCoursePage />} />
            <Route path="coursework/:id" element={<CourseworkReviewPage />} />
          </>
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routed />
      </BrowserRouter>
    </AuthProvider>
  )
}
