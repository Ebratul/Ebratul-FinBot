"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import { 
  listUsers, createUser, deleteUser, updateUserRole, 
  listDocuments, uploadDocument, deleteDocument, listRoles,
  getEvaluationDataset, runEvaluation, getLatestEvaluationResults
} from "@/lib/api";
import Navbar from "@/components/Navbar";
import styles from "./admin.module.css";

const MetricCard = ({ label, baseline, final, description }) => {
  const delta = (final - baseline) * 100;
  return (
    <div className={styles.metricCard}>
      <div className={styles.metricLabel}>{label}</div>
      <div className={styles.metricValueContainer}>
        <span className={styles.metricValueBaseline}>{(baseline * 100).toFixed(0)}%</span>
        <span className={styles.metricValueFinal}>{(final * 100).toFixed(0)}%</span>
      </div>
      <div className={`${styles.metricDelta} ${delta >= 0 ? styles.deltaPositive : styles.deltaNegative}`}>
        {delta >= 0 ? '+' : ''}{delta.toFixed(0)}% Improvement
      </div>
      <div className={styles.metricNote}>{description}</div>
    </div>
  );
};

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  
  const [users, setUsers] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [roles, setRoles] = useState({});
  const [evaluationDataset, setEvaluationDataset] = useState([]);
  const [evaluationResults, setEvaluationResults] = useState(null);
  const [activeTab, setActiveTab] = useState("users");
  const [evalSampleSize, setEvalSampleSize] = useState(10);
  
  // User Form State
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("employee");
  const [newDisplayName, setNewDisplayName] = useState("");
  
  // Document Upload State
  const [selectedFile, setSelectedFile] = useState(null);
  const [targetCollection, setTargetCollection] = useState("general");
  
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      const [uData, dData, rData, eData, resData] = await Promise.all([
        listUsers(),
        listDocuments(),
        listRoles(),
        getEvaluationDataset(),
        getLatestEvaluationResults(),
      ]);
      setUsers(uData);
      setDocuments(dData);
      setRoles(rData);
      setEvaluationDataset(eData);
      setEvaluationResults(resData);
    } catch (err) {
      setError(err.message || "Failed to fetch admin data.");
    }
  }, []);

  useEffect(() => {
    if (!loading && (!user || !user.is_admin)) {
      router.push("/chat");
      return;
    }
    if (user?.is_admin) {
      fetchData();
    }
  }, [user, loading, router, fetchData]);

  if (loading || !user || !user.is_admin) return <div className="page">Loading...</div>;

  const handleCreateUser = async (e) => {
    e.preventDefault();
    setIsProcessing(true);
    setError(null);
    try {
      await createUser(newUsername, newPassword, newRole, newDisplayName);
      setSuccess(`User ${newUsername} created successfully.`);
      setNewUsername("");
      setNewPassword("");
      setNewDisplayName("");
      fetchData();
    } catch (err) {
      setError(err.message || "Failed to create user.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!confirm("Are you sure you want to delete this user?")) return;
    setIsProcessing(true);
    try {
      await deleteUser(userId);
      setSuccess("User deleted.");
      fetchData();
    } catch (err) {
      setError(err.message || "Failed to delete user.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleUpdateRole = async (userId, role) => {
    setIsProcessing(true);
    try {
      await updateUserRole(userId, role);
      setSuccess("Role updated.");
      fetchData();
    } catch (err) {
      setError(err.message || "Failed to update role.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    setIsProcessing(true);
    setError(null);
    try {
      await uploadDocument(selectedFile, targetCollection);
      setSuccess(`Document ${selectedFile.name} uploaded and indexed.`);
      setSelectedFile(null);
      // Reset file input
      e.target.reset();
      fetchData();
    } catch (err) {
      setError(err.message || "Upload failed.");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDeleteDoc = async (collection, filename) => {
    if (!confirm("Are you sure you want to delete this document?")) return;
    setIsProcessing(true);
    try {
      await deleteDocument(collection, filename);
      setSuccess("Document deleted.");
      fetchData();
    } catch (err) {
      setError(err.message || "Failed to delete document.");
    } finally {
      setIsProcessing(false);
    }
  };
  const handleRunEvaluation = async () => {
    setIsProcessing(true);
    setSuccess(null);
    setError(null);
    try {
      const results = await runEvaluation(evalSampleSize);
      setEvaluationResults(results);
      setSuccess("Evaluation completed successfully.");
    } catch (err) {
      setError(err.message || "Evaluation failed.");
    } finally {
      setIsProcessing(false);
    }
  };

  const renderEvaluation = () => {
    const baselineAvg = evaluationResults?.baseline ? calculateAverages(evaluationResults.baseline) : null;
    const finalAvg = evaluationResults?.final ? calculateAverages(evaluationResults.final) : null;

    return (
      <div className={styles.sectionGridFull}>
        <div className={styles.createCard}>
          <h2 className={styles.sectionTitle}>Run RAGAs Evaluation</h2>
          <div className={styles.formGroup}>
            <label className="input-label">Sample Size (Limit for Speed)</label>
            <p className={styles.userSubtitle}>Running full 45-pair evaluation takes ~5 minutes. Start with 5-10 for testing.</p>
            <select className="select" value={evalSampleSize} onChange={(e) => setEvalSampleSize(Number(e.target.value))}>
              <option value={5}>5 Questions</option>
              <option value={10}>10 Questions</option>
              <option value={20}>20 Questions</option>
              <option value={45}>All 45 Questions</option>
            </select>
          </div>
          <button 
            className="btn btn-primary btn-lg" 
            onClick={handleRunEvaluation} 
            disabled={isProcessing}
            style={{ width: '100%', marginTop: 10 }}
          >
            {isProcessing ? "🚀 Evaluating (LLM + RAGAs)..." : "🧪 Start Ablation Study"}
          </button>
        </div>

        {evaluationResults && evaluationResults.baseline && (
          <div className={styles.resultsDashboard}>
            <h2 className={styles.sectionTitle}>Ablation Study: Guardrails Impact</h2>
            
            <div className={styles.metricComparisonGrid}>
              <MetricCard 
                label="Faithfulness" 
                baseline={baselineAvg?.faithfulness} 
                final={finalAvg?.faithfulness} 
                description="Are answers grounded in context?"
              />
              <MetricCard 
                label="Correctness" 
                baseline={baselineAvg?.answer_correctness} 
                final={finalAvg?.answer_correctness} 
                description="Accuracy against ground truth"
              />
              <MetricCard 
                label="Relevancy" 
                baseline={baselineAvg?.answer_relevancy} 
                final={finalAvg?.answer_relevancy} 
                description="Relevance to user question"
              />
              <MetricCard 
                label="Context Precision" 
                baseline={baselineAvg?.context_precision} 
                final={finalAvg?.context_precision} 
                description="Retrieval accuracy"
              />
            </div>

            <div className={styles.tableCard} style={{ marginTop: 30 }}>
              <h3 className={styles.sectionTitle}>Detailed Ablation Logs</h3>
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Question</th>
                      <th>Baseline (Off)</th>
                      <th>Final (On)</th>
                      <th>Delta</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluationResults.dataset.map((item, idx) => {
                      const b = evaluationResults.baseline[idx];
                      const f = evaluationResults.final[idx];
                      const bScore = b?.faithfulness || 0;
                      const fScore = f?.faithfulness || 0;
                      const delta = fScore - bScore;
                      
                      return (
                        <tr key={idx}>
                          <td style={{ maxWidth: 300 }}>{item.question}</td>
                          <td><span className="badge badge-error">{(bScore * 100).toFixed(0)}%</span></td>
                          <td><span className="badge badge-success">{(fScore * 100).toFixed(0)}%</span></td>
                          <td style={{ fontWeight: 600, color: delta >= 0 ? 'var(--success)' : 'var(--error)' }}>
                            {delta >= 0 ? '+' : ''}{(delta * 100).toFixed(0)}%
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        <div className={styles.tableCard} style={{ gridColumn: 'span 1' }}>
          <h2 className={styles.sectionTitle}>Ground Truth Dataset ({evaluationDataset.length} Pairs)</h2>
          <div className={styles.tableWrapper} style={{ maxHeight: 500 }}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Benchmark Question</th>
                  <th>Ground Truth Answer</th>
                </tr>
              </thead>
              <tbody>
                {evaluationDataset.map((item, idx) => (
                  <tr key={idx}>
                    <td style={{ width: '40%' }}><strong>{item.question}</strong></td>
                    <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>{item.ground_truth}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    );
  };

  const calculateAverages = (list) => {
    if (!list || list.length === 0) return {};
    const keys = ["faithfulness", "answer_correctness", "answer_relevancy", "context_precision", "context_recall"];
    const avgs = {};
    keys.forEach(k => {
      const sum = list.reduce((acc, curr) => acc + (curr[k] || 0), 0);
      avgs[k] = sum / list.length;
    });
    return avgs;
  };

  return (
    <div className={styles.adminLayout}>
      <Navbar />
      
      <main className={styles.main}>
        <div className="container">
          <header className={styles.header}>
            <div className={styles.headerInfo}>
              <h1 className={styles.title}>Admin Panel</h1>
              <p className={styles.subtitle}>Manage Users, Roles, and Document Collections</p>
            </div>
            <div className={styles.tabs}>
              <button 
                className={`${styles.tab} ${activeTab === 'users' ? styles.activeTab : ''}`}
                onClick={() => setActiveTab('users')}
              >
                👤 Manage Users
              </button>
              <button 
                className={`${styles.tab} ${activeTab === 'docs' ? styles.activeTab : ''}`}
                onClick={() => setActiveTab('docs')}
              >
                📂 Document Collections
              </button>
              <button 
                className={`${styles.tab} ${activeTab === 'eval' ? styles.activeTab : ''}`}
                onClick={() => setActiveTab('eval')}
              >
                🧪 Evaluation
              </button>
            </div>
          </header>

          {error && <div className="alert alert-error animate-slide-up" style={{ marginBottom: 20 }}>{error}</div>}
          {success && <div className="alert alert-success animate-slide-up" style={{ marginBottom: 20 }}>{success}</div>}

          {activeTab === 'users' ? (
            <div className={styles.sectionGrid}>
              <div className={styles.createCard}>
                <h2 className={styles.sectionTitle}>Add New User</h2>
                <form className={styles.form} onSubmit={handleCreateUser}>
                  <div className={styles.formGroup}>
                    <label className="input-label">User's Full Name</label>
                    <input className="input" value={newDisplayName} onChange={(e) => setNewDisplayName(e.target.value)} required placeholder="e.g. John Doe" />
                  </div>
                  <div className={styles.formGroup}>
                    <label className="input-label">Username</label>
                    <input className="input" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} required placeholder="e.g. john" />
                  </div>
                  <div className={styles.formGroup}>
                    <label className="input-label">Password</label>
                    <input className="input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} required placeholder="••••••••" />
                  </div>
                  <div className={styles.formGroup}>
                    <label className="input-label">Departmental Role</label>
                    <select className="select" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                      {Object.keys(roles).map(r => (
                        <option key={r} value={r}>{r.replace('_', ' ').toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                  <button type="submit" className="btn btn-primary btn-lg" disabled={isProcessing}>
                    {isProcessing ? "Creating..." : "Create User Account"}
                  </button>
                </form>
              </div>

              <div className={styles.tableCard}>
                <h2 className={styles.sectionTitle}>System Users</h2>
                <div className={styles.tableWrapper}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Role</th>
                        <th>System Access</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map(u => (
                        <tr key={u.id}>
                          <td>
                            <div className={styles.userInfo}>
                              <span className={styles.userName}>{u.display_name}</span>
                              <span className={styles.userSubtitle}>{u.username} {u.is_admin ? '(Admin)' : ''}</span>
                            </div>
                          </td>
                          <td>
                            <select 
                              className={styles.inlineSelect} 
                              value={u.role} 
                              onChange={(e) => handleUpdateRole(u.id, e.target.value)}
                              disabled={isProcessing || u.id === user.id}
                            >
                              {Object.keys(roles).map(r => (
                                <option key={r} value={r}>{r}</option>
                              ))}
                            </select>
                          </td>
                          <td>
                            <div className={styles.tagList}>
                              {u.accessible_collections.map(c => (
                                <span key={c} className="badge badge-gold">{c}</span>
                              ))}
                            </div>
                          </td>
                          <td>
                            <button 
                              className="btn btn-danger btn-sm" 
                              onClick={() => handleDeleteUser(u.id)}
                              disabled={isProcessing || u.id === user.id}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : activeTab === 'docs' ? (
            <div className={styles.sectionGrid}>
              <div className={styles.createCard}>
                <h2 className={styles.sectionTitle}>Upload New Document</h2>
                {/* ... existing upload form code ... */}
                <form className={styles.form} onSubmit={handleUpload}>
                  <div className={styles.formGroup}>
                    <label className="input-label">Target Collection</label>
                    <p style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>
                      The collection determines which roles can retrieve this doc.
                    </p>
                    <select className="select" value={targetCollection} onChange={(e) => setTargetCollection(e.target.value)}>
                      {["general", "finance", "engineering", "marketing"].map(c => (
                        <option key={c} value={c}>{c.toUpperCase()}</option>
                      ))}
                    </select>
                  </div>
                  <div className={styles.formGroup}>
                    <label className="input-label">Select File (PDF, DOCX, MD, TXT)</label>
                    <input 
                      className="input" 
                      type="file" 
                      accept=".pdf,.docx,.doc,.md,.txt" 
                      onChange={(e) => setSelectedFile(e.target.files[0])}
                      required
                    />
                  </div>
                  <button type="submit" className="btn btn-primary btn-lg" disabled={isProcessing || !selectedFile}>
                    {isProcessing ? "Processing & Indexing..." : "Upload & Index Document"}
                  </button>
                </form>
              </div>

              <div className={styles.tableCard}>
                <h2 className={styles.sectionTitle}>Document Repository</h2>
                <div className={styles.tableWrapper}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Filename</th>
                        <th>Collection</th>
                        <th>Size</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {documents.map((doc, idx) => (
                        <tr key={idx}>
                          <td><span className={styles.docName}>📄 {doc.filename}</span></td>
                          <td><span className="badge badge-info">{doc.collection}</span></td>
                          <td><span className={styles.docSize}>{(doc.size_bytes / 1024).toFixed(1)} KB</span></td>
                          <td>
                            <button 
                              className="btn btn-danger btn-sm" 
                              onClick={() => handleDeleteDoc(doc.collection, doc.filename)}
                              disabled={isProcessing}
                            >
                              Remove
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            renderEvaluation()
          )}
        </div>
      </main>
    </div>
  );
}
