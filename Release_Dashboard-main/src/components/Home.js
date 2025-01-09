import React, { useState, useEffect } from 'react';
import './Home.css';
import Navbar from './Navbar';
import Updatedtime from './Updatedtime';
import Dropdown from './Dropbox';
import Table from './Table';

function Home() {
  const [selectedCluster, setSelectedCluster] = useState('');
  const [selectedEnvironment, setSelectedEnvironment] = useState('');
  const [selectedNamespace, setSelectedNamespace] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [environmentData, setEnvironmentData] = useState([]);
  const [environmentTime, setEnvironmentTime] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSearch = (term) => {
    setSearchTerm(term);
  };

  const handleEnvironmentSelect = (env) => {
    setSelectedEnvironment(env);
    setSelectedCluster('');
    setSelectedNamespace('');
  };

  const handleClusterSelect = (cluster) => {
    setSelectedCluster(cluster);
    setSelectedNamespace('');
  };

  const handleNamespaceSelect = (namespace) => {
    setSelectedNamespace(namespace);
  };

  // Fetch environment data when the environment changes
  useEffect(() => {
    if (!selectedEnvironment) {
      setEnvironmentData([]);
      setEnvironmentTime([])
      return;
    }

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`http://127.0.0.1:5000/api/${selectedEnvironment}`);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setEnvironmentData(data.data || []);
        setEnvironmentTime(data.time || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [selectedEnvironment]);

  const refreshEnv = async () => {
    setLoading(true);
    setError(null);
    try{
    const response = await fetch(`http://127.0.0.1:5000/api/cache/refresh/${selectedEnvironment}`, {
      method: 'POST',  
      headers: {
        'Content-Type': 'application/json', 
      }
    });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setEnvironmentData(data.data || []);
      setEnvironmentTime(data.time || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
};

  return (
    <div>
      <Navbar />
      <div className="header-container">
        <h1 className="title">Release Dashboard</h1>
        <div className="time-container">
          <Updatedtime environmentTime={environmentTime} />
          <button onClick={refreshEnv} className="refresh-button">↻</button>
        </div>
      </div>

      <Dropdown
        onSearch={handleSearch}
        onSelectEnvironment={handleEnvironmentSelect}
        onSelectCluster={handleClusterSelect}
        onSelectNamespace={handleNamespaceSelect}
        selectedCluster={selectedCluster}
        environmentData={environmentData}
      />

      <Table
        searchTerm={searchTerm}
        selectedCluster={selectedCluster}
        selectedEnvironment={selectedEnvironment}
        selectedNamespace={selectedNamespace}
        environmentData={environmentData}
        loading={loading}
        error={error}
      />
    </div>
  );
}

export default Home;
