import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Extension from './extension.component';

const Root: React.FC = () => (
  <BrowserRouter basename={window.getOpenmrsSpaBase()}>
    <Routes>
      <Route path="extension" element={<Extension />} />
    </Routes>
  </BrowserRouter>
);

export default Root;
