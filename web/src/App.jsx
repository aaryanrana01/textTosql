import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { getToken, readUser, saveSession, setUnauthorizedHandler } from './api.js';
import AuthScreen from './components/AuthScreen.jsx';
import Workspace from './components/Workspace.jsx';

export default function App() {
  const queryClient = useQueryClient();
  const [user, setUser] = useState(() => (getToken() ? readUser() : null));

  function signIn({ token, user: signedIn }) {
    saveSession(token, signedIn);
    setUser(signedIn);
  }

  function signOut() {
    saveSession(null);
    queryClient.clear(); // drop the previous user's cached history
    setUser(null);
  }

  useEffect(() => {
    setUnauthorizedHandler(signOut);
  }, []);

  return user ? <Workspace user={user} onSignOut={signOut} /> : <AuthScreen onSignedIn={signIn} />;
}