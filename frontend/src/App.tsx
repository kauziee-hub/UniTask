import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Shell } from './components/Shell'
import { Spinner } from './components/ui'
import { AuthProvider, useAuth } from './lib/auth'
import { AuthPage } from './pages/AuthPage'
import { ClassesPage } from './pages/student/ClassesPage'
import { ConnectionsPage } from './pages/student/ConnectionsPage'
import { ExamPage, ExamsPage } from './pages/student/ExamsPage'
import { InboxPage } from './pages/student/InboxPage'
import { InsightsPage } from './pages/student/InsightsPage'
import { LibraryPage } from './pages/student/LibraryPage'
import { MaterialPage } from './pages/student/MaterialPage'
import { PlannerPage } from './pages/student/PlannerPage'
import { RevisionPage } from './pages/student/RevisionPage'
import { SettingsPage } from './pages/student/SettingsPage'
import { StudentCoursePage } from './pages/student/StudentCoursePage'
import { StudyDeskPage } from './pages/student/StudyDeskPage'
import { SubjectPage } from './pages/student/SubjectPage'
import { SubjectsPage } from './pages/student/SubjectsPage'
import { TodayPage } from './pages/student/TodayPage'
import { TopicPage } from './pages/student/TopicPage'
import { TutorPage } from './pages/student/TutorPage'
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
            <Route path="inbox" element={<InboxPage />} />
            <Route path="work" element={<WorkPage />} />
            <Route path="work/:id" element={<WorkDetailPage />} />
            <Route path="planner" element={<PlannerPage />} />
            <Route path="exams" element={<ExamsPage />} />
            <Route path="exams/:id" element={<ExamPage />} />
            <Route path="subjects" element={<SubjectsPage />} />
            <Route path="subjects/:id" element={<SubjectPage />} />
            <Route path="topics/:id" element={<TopicPage />} />
            <Route path="library" element={<LibraryPage />} />
            <Route path="library/:id" element={<MaterialPage />} />
            <Route path="study/:id" element={<StudyDeskPage />} />
            <Route path="revision" element={<RevisionPage />} />
            <Route path="tutor" element={<TutorPage />} />
            <Route path="insights" element={<InsightsPage />} />
            <Route path="classes" element={<ClassesPage />} />
            <Route path="classes/:id" element={<StudentCoursePage />} />
            <Route path="connections" element={<ConnectionsPage />} />
            <Route path="settings" element={<SettingsPage />} />
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
