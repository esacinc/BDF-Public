import React from 'react';

const LoadingBar = () => {
  const message = props.message || "Loading, please wait...";

  const containerStyle = {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    margin: '10px 0 0 40px',
    fontFamily: 'Segoe UI, Roboto, sans-serif',
    color: '#333',
  };

  const barStyle = {
    position: 'relative',
    width: '320px',
    height: '12px',
    backgroundColor: '#f5f5f5',
    overflow: 'hidden',
    borderRadius: '6px',
    boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.1)',
    marginBottom: '10px',
  };

  const innerBarStyle = {
    position: 'absolute',
    width: '30%',
    height: '100%',
    background: 'linear-gradient(270deg, #ff6ec4, #7873f5, #00c6ff, #0072ff, #ff6ec4)',
    backgroundSize: '800% 800%',
    borderRadius: '6px',
    animation: 'gradient-slide 4s ease-in-out infinite',
    boxShadow: '0 0 10px rgba(120, 115, 245, 0.6)',
  };

  const keyframes = `
    @keyframes gradient-slide {
      0% { left: -30%; background-position: 0% 50%; }
      50% { left: 100%; background-position: 100% 50%; }
      100% { left: -30%; background-position: 0% 50%; }
    }
  `;

  return (
    <div style={containerStyle}>
      <style>{keyframes}</style>
      <div style={barStyle}>
        <div style={innerBarStyle}></div>
      </div>
      <p style={{ margin: 0, fontSize: '14px', color: '#666' }}>{message}</p>
    </div>
  );
};

export default LoadingBar;
