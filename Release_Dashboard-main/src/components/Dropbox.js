import React, { useState } from 'react';
import './Dropbox.css';

const Dropdown = ({ onSearch, onSelectEnvironment, onSelectCluster, onSelectNamespace, selectedCluster, environmentData}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [namespaces, setNamespaces] = useState([]);
  const [mappedClusters, setMappedClusters] = useState([]);

  const envToClusterMap = {
    poc: ['aks-pe-poc', 'minikube'],
    dev: ['minikube'],
    prod: [],
  };

  const handleSearchChange = (event) => {
    const value = event.target.value;
    setSearchTerm(value);
    onSearch(value);
  };

  const handleEnvironmentChange = (event) => {
    const environment = event.target.value;
    onSelectEnvironment(environment);
    setMappedClusters(envToClusterMap[environment] || []);
    setSearchTerm('');
    onSearch('');
    setNamespaces([]);
    onSelectCluster(null);
    onSelectNamespace('');
  };

  const handleClusterChange = (event) => {
    const cluster = event.target.value;
    onSelectCluster(cluster);
    onSelectNamespace('');

    if (cluster) {
      const filteredNamespaces = [
        ...new Set(
          environmentData
            .filter((item) => item.cluster === cluster)
            .map((item) => item.namespace)
        ),
      ];
      setNamespaces(filteredNamespaces);
    } else {
      setNamespaces([]);
    }
  };

  const handleNamespaceChange = (event) => {
    onSelectNamespace(event.target.value);
  };

  return (
    <div className="dropdown-container">
      <div className="dropdown-item">
        <label htmlFor="env">Environment:</label>
        <select id="env" onChange={handleEnvironmentChange}>
          <option value="">--Select Environment--</option>
          {Object.keys(envToClusterMap).map((env) => (
            <option key={env} value={env}>
              {env}
            </option>
          ))}
        </select>
      </div>

      <div className="dropdown-item">
        <label htmlFor="cluster">Cluster:</label>
        <select
          id="cluster"
          onChange={handleClusterChange}
          disabled={mappedClusters.length === 0}
        >
          <option value="">--Select Cluster--</option>
          {mappedClusters.map((cluster) => (
            <option key={cluster} value={cluster}>
              {cluster}
            </option>
          ))}
        </select>
      </div>

      {selectedCluster && (
        <div className="dropdown-item">
          <label htmlFor="namespace">Namespace:</label>
          <select id="namespace" onChange={handleNamespaceChange}>
            <option value="">--Select Namespace--</option>
            {namespaces.map((namespace, index) => (
              <option key={index} value={namespace}>
                {namespace}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="search-bar">
        <label htmlFor="search">Search Records:</label>
        <input
          type="text"
          id="search"
          placeholder="Search..."
          value={searchTerm}
          onChange={handleSearchChange}
        />
      </div>
    </div>
  );
};

export default Dropdown;
