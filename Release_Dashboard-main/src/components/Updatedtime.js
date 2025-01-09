import React from 'react'
import './Updatedtime.css';

const Updatedtime = ({ environmentTime }) => {
    const displayTime = environmentTime && environmentTime.length > 0 ? environmentTime : "None selected";

    return (
      <div>
        <h4 className="time-display"> 
          Last Updated:   
          <span className="time">{displayTime}</span> 
        </h4>
      </div>
    );
  };
  

export default Updatedtime