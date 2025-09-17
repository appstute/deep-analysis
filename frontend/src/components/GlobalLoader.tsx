import React, { useEffect, useState } from 'react';
import './GlobalLoader.css';

interface GlobalLoaderProps {
  isLoading: boolean;
}

const GlobalLoader: React.FC<GlobalLoaderProps> = ({ isLoading }) => {
  const [visible, setVisible] = useState(false);
  
  useEffect(() => {
    let timeoutId: NodeJS.Timeout;
    
    // Add a small delay before showing the loader to prevent flashing
    // for very quick requests
    if (isLoading) {
      timeoutId = setTimeout(() => {
        setVisible(true);
      }, 300); // Increased delay to prevent flashing for quick requests
    } else {
      setVisible(false);
    }
    
    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [isLoading]);

  return (
    <div className={`global-loader ${visible ? 'visible' : ''}`}>
      <div className="spinner" />
    </div>
  );
};

export default GlobalLoader;
