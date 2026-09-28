import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import App from './App'
import Dashboard from './pages/Dashboard'
import IncidentDetail from './pages/IncidentDetail'
import MemoryView from './pages/MemoryView'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<Dashboard />} />
          <Route path="incidents/:ref" element={<IncidentDetail />} />
          <Route path="memory" element={<MemoryView />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
