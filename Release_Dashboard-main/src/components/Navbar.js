import React from 'react'
import './Navbar.css'
import logo from '../assets/Cogniwide_logo.png'

const Navbar = () => {
  return (
    <nav className="navbar">
       <img src={logo} alt="Logo" className="logo" /> 
      <span className="app-name">COGNICLOUD</span>
    </nav>
  );
}

export default Navbar