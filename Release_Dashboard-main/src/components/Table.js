import React, { useState } from 'react';
import './Table.css';
import Pagination from './Pagination';

const DynamicTable = ({ searchTerm, selectedCluster, selectedNamespace, environmentData, loading, error}) => {
  const [sortConfig, setSortConfig] = useState({ key: '', direction: '' });
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 20;

  const handleSort = (key, direction) => {
    setSortConfig({ key, direction });
  };

  const sortedData = [...environmentData].sort((a, b) => {
    if (!sortConfig.key) return 0;

    const order = sortConfig.direction === 'asc' ? 1 : -1;
    const getFieldValue = (item, key) => {
      switch (key) {
        case 'version':
          return item['main-containers']?.[0]?.version || '';
        case 'mainImage':
          return item['main-containers']?.[0]?.image || '';
        case 'initImages':
          return item['init-containers']?.map((container) => container.image).join(', ') || '';
        default:
          return item[key] || '';
      }
    };

    const aValue = getFieldValue(a, sortConfig.key);
    const bValue = getFieldValue(b, sortConfig.key);

    if (typeof aValue === 'string' && typeof bValue === 'string') {
      return aValue.localeCompare(bValue) * order;
    }
    return (aValue > bValue ? 1 : -1) * order;
  });

  const filteredData = sortedData
    .filter((item) => (selectedCluster ? item.cluster === selectedCluster : true))
    .filter((item) => {
      const search = (field) =>
        field &&
        typeof field === 'string' &&
        field.toLowerCase().includes(searchTerm.toLowerCase());

      return (
        (searchTerm === '' ||
          search(item['deployment-name']) ||
          search(item.namespace) ||
          item['main-containers']?.some((container) =>
            container.image.toLowerCase().includes(searchTerm.toLowerCase())
          ) ||
          item['init-containers']?.some((container) =>
            container.image.toLowerCase().includes(searchTerm.toLowerCase())
          )) &&
        (selectedNamespace === '' || item.namespace === selectedNamespace)
      );
    });

  const totalItems = filteredData.length;
  const startIndex = (currentPage - 1) * itemsPerPage;
  const currentItems = filteredData.slice(startIndex, startIndex + itemsPerPage);

  return (
    <div>
      <table className="table">
        <thead>
          <tr>
            <th>
              <div className="table-header-content">
                <span className="table-heading">Deployment Name</span>
                <div className="sort-arrows">
                  <span onClick={() => handleSort('deployment-name', 'asc')} className="arrow">▲</span>
                  <span onClick={() => handleSort('deployment-name', 'desc')} className="arrow">▼</span>
                </div>
              </div>
            </th>
            <th>
              <div className="table-header-content">
                <span className="table-heading">Namespace</span>
                <div className="sort-arrows">
                  <span onClick={() => handleSort('namespace', 'asc')} className="arrow">▲</span>
                  <span onClick={() => handleSort('namespace', 'desc')} className="arrow">▼</span>
                </div>
              </div>
            </th>
            <th>
              <div className="table-header-content">
                <span className="table-heading">Cluster Name</span>
                <div className="sort-arrows">
                  <span onClick={() => handleSort('cluster', 'asc')} className="arrow">▲</span>
                  <span onClick={() => handleSort('cluster', 'desc')} className="arrow">▼</span>
                </div>
              </div>
            </th>
            <th>
              <div className="table-header-content">
                <span className="table-heading">Main Container Images</span>
                <div className="sort-arrows">
                  <span onClick={() => handleSort('mainImage', 'asc')} className="arrow">▲</span>
                  <span onClick={() => handleSort('mainImage', 'desc')} className="arrow">▼</span>
                </div>
              </div>
            </th>
            <th>
              <div className="table-header-content">
                <span className="table-heading">Version</span>
                <div className="sort-arrows">
                  <span onClick={() => handleSort('version', 'asc')} className="arrow">▲</span>
                  <span onClick={() => handleSort('version', 'desc')} className="arrow">▼</span>
                </div>
              </div>
            </th>
            <th>
              <div className="table-header-content">
                <span className="table-heading">Side Container Images</span>
                <div className="sort-arrows">
                  <span onClick={() => handleSort('initImages', 'asc')} className="arrow">▲</span>
                  <span onClick={() => handleSort('initImages', 'desc')} className="arrow">▼</span>
                </div>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan="6" style={{ textAlign: 'center', color: '#206cb8', fontSize: '18px' }}>
                Loading data...
              </td>
            </tr>
          )}
          {error && (
            <tr>
              <td colSpan="6" style={{ textAlign: 'center', color: 'red', fontSize: '18px' }}>
                Error: {error}
              </td>
            </tr>
          )}

          {!loading &&
            !error &&
            currentItems.map((item, index) => {
              const mainImages = item['main-containers'];
              const initImages = item['init-containers'];

              const rows = mainImages.map((container, idx) => ({
                deploymentName: item['deployment-name'],
                namespace: item.namespace,
                clusterName: item.cluster || 'Unknown',
                version: container.version,
                mainImage: container.image.split(':')[0],
                initImages: initImages
                  .map((initContainer) => initContainer.image)
                  .join(', '),
              }));

              return rows.map((row, rowIndex) => (
                <tr key={`${index}-${rowIndex}`}>
                  <td>{row.deploymentName}</td>
                  <td>{row.namespace || 'N/A'}</td>
                  <td>{row.clusterName}</td>
                  <td>{row.mainImage}</td>
                  <td>{row.version}</td>
                  <td>{row.initImages || 'N/A'}</td>
                </tr>
              ));
            })}
        </tbody>
      </table>

      {totalItems > 0 && (
        <Pagination
          currentPage={currentPage}
          totalItems={totalItems}
          itemsPerPage={itemsPerPage}
          onPageChange={setCurrentPage}
        />
      )}
    </div>
  );
};

export default DynamicTable;
