import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import RootLayout from './layouts/RootLayout';
import Home from './pages/Home';
import Dashboard from './pages/Dashboard';
import Alarms from './pages/Alarms';
import Challenge from './pages/Challenge';
import Wake from './pages/Wake';
import History from './pages/History';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<RootLayout />}>
          <Route index element={<Home />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="alarms" element={<Alarms />} />
          <Route path="challenge" element={<Challenge />} />
          <Route path="wake" element={<Wake />} />
          <Route path="history" element={<History />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
