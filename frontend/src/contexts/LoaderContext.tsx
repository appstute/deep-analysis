import React, { createContext, useContext, useState } from 'react';

interface LoaderContextType {
  setLoading: (isLoading: boolean) => void;
  isLoading: boolean;
}

const LoaderContext = createContext<LoaderContextType>({
  setLoading: () => {},
  isLoading: false,
});

export const useLoader = () => useContext(LoaderContext);

export const LoaderProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isLoading, setIsLoading] = useState(false);
  
  return (
    <LoaderContext.Provider value={{ isLoading, setLoading: setIsLoading }}>
      {children}
    </LoaderContext.Provider>
  );
};
