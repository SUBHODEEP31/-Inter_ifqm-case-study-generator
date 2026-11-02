'use strict';
'use client';

import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Building2, Upload, Search, Sliders, CheckSquare, Terminal, 
  BookOpen, Download, AlertTriangle, Play, ChevronRight, Plus, 
  RotateCw, Check, Sparkles, FileText, HelpCircle, Edit3, Save, RefreshCw,
  Database, ShieldCheck, CheckCircle
} from 'lucide-react';

const IFQM_MAIN_URL = "https://ifqm.org.in/";

const IFQM_NAV_LINKS = [
  { name: "Home", href: IFQM_MAIN_URL },
  { name: "About Us", href: IFQM_MAIN_URL },
  { name: "Offerings", href: IFQM_MAIN_URL },
  { name: "Courses", href: IFQM_MAIN_URL },
  { name: "Events", href: IFQM_MAIN_URL },
  { name: "Contact Us", href: IFQM_MAIN_URL }
];

export default function Workstation() {
  // Navigation & Pipeline State
  const [screen, setScreen] = useState(0);
  const [sessionId, setSessionId] = useState(null);
  const [status, setStatus] = useState("idle");
  const [logs, setLogs] = useState([]);
  const [error, setError] = useState(null);
  const [activeModal, setActiveModal] = useState(null); // 'about' | 'offerings' | 'contact' | null

  const handleNavClick = (name) => {
    if (name === "Home") {
      setScreen(0);
      setActiveModal(null);
    } else if (name === "About Us") {
      setActiveModal('about');
    } else if (name === "Offerings" || name === "Courses" || name === "Events") {
      setActiveModal('offerings');
    } else if (name === "Contact Us") {
      setActiveModal('contact');
    } else {
      setActiveModal('about');
    }
  };

  // Screen 1: Company Profile Configuration
  const [companyName, setCompanyName] = useState("");
  const [sector, setSector] = useState("");
  const [region, setRegion] = useState("");
  const [timeline, setTimeline] = useState("");

  // Screen 2: Context Ingestion
  const [rawTextContext, setRawTextContext] = useState("");
  const [annualReport, setAnnualReport] = useState(null);
  const [transcript, setTranscript] = useState(null);
  const [voiceRecord, setVoiceRecord] = useState(null);

  // Screen 3: Scraper Settings
  const [manualUrls, setManualUrls] = useState("");
  const [autoScrape, setAutoScrape] = useState(true);

  // Screen 4: Pre-Gen Parameters
  const [archetype, setArchetype] = useState("Explanatory");
  const [targetPages, setTargetPages] = useState(20);
  const [includeTeachingNote, setIncludeTeachingNote] = useState(true);
  const [excludedChapters, setExcludedChapters] = useState(["Future Scope"]);

  // Screen 7: Active Workspace State
  const [briefData, setBriefData] = useState(null);
  const [isEditingBrief, setIsEditingBrief] = useState(false);
  const [chapters, setChapters] = useState({
    "Opening Hook": "",
    "Company Background": "",
    "Industry & Competitive Context": "",
    "The Challenge": "",
    "Root Cause Analysis": "",
    "Approach / Solution": "",
    "Implementation": "",
    "Results and Impact": "",
    "Key Learnings": "",
    "Recommendations": "",
    "Future Scope": "",
    "Discussion Questions": "",
    "Teaching Note: Learning Objectives": ""
  });
  const [activeChapter, setActiveChapter] = useState("Opening Hook");
  const [steeragePrompt, setSteeragePrompt] = useState("");
  const [customOverviewData, setCustomOverviewData] = useState("");
  const [streamingContent, setStreamingContent] = useState("");
  const [approvedChapters, setApprovedChapters] = useState([]);
  
  // Custom custom sections list
  const [customSections, setCustomSections] = useState([]);
  const [newSectionTitle, setNewSectionTitle] = useState("");
  const [newSectionType, setNewSectionType] = useState("prose");

  // Fact Friction Warning Trigger
  const [frictionConflict, setFrictionConflict] = useState(null);

  // Live Exhibit spreadsheet data
  const [exhibits, setExhibits] = useState([
    { id: 1, metric: "Operating Margin (%)", val2022: "14.5%", val2023: "12.1%", source: "Annual Audit" },
    { id: 2, metric: "Factory Floor Defect Rate", val2022: "0.45%", val2023: "1.12%", source: "Quality Framework" },
    { id: 3, metric: "R&D Capex ($M)", val2022: "450", val2023: "520", source: "Financial Statements" }
  ]);

  const logsEndRef = useRef(null);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  useEffect(() => {
    if (targetPages === 10) {
      setExcludedChapters(["Industry & Competitive Context", "Key Learnings", "Recommendations", "Future Scope"]);
    } else if (targetPages === 20) {
      setExcludedChapters(["Future Scope"]);
    } else if (targetPages === 30) {
      setExcludedChapters([]);
    }
  }, [targetPages]);

  // Live API Connection parameters
  const apiBase = "http://localhost:8000";

  // Starts the ingestion pipeline via the live FastAPI backend
  const startIngestPipeline = async () => {
    if (status === "processing") return;
    setScreen(6);
    setLogs(["[INFO] Preparing document payload form data..."]);
    setStatus("processing");

    try {
      const formData = new FormData();
      formData.append("company_name", companyName);
      if (rawTextContext) formData.append("raw_text_context", rawTextContext);
      if (annualReport) formData.append("annual_disclosure", annualReport);
      if (transcript) formData.append("meeting_transcript", transcript);
      if (voiceRecord) formData.append("voice_audio", voiceRecord);

      setLogs(prev => [...prev, "[INFO] Posting files to FastAPI Ingest Endpoint..."]);
      const res = await fetch(`${apiBase}/api/ingest`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Backend connection failed during upload.");
      }

      const data = await res.json();
      const sid = data.session_id;
      setSessionId(sid);

      setLogs(prev => [...prev, `[INFO] Upload success. Session ID assigned: ${sid}`]);
      setLogs(prev => [...prev, "[INFO] Waiting for background parser cores..."]);

      // Poll status endpoint every 2 seconds
      const interval = setInterval(async () => {
        try {
          const statusRes = await fetch(`${apiBase}/api/ingest/status/${sid}`);
          if (!statusRes.ok) throw new Error("Status query failed.");
          const statusData = await statusRes.json();

          if (statusData.status === "ingesting") {
            setLogs(prev => {
              if (prev[prev.length - 1] !== "[INFO] Status: Ingesting & OCR layout parsing...") {
                return [...prev, "[INFO] Status: Ingesting & OCR layout parsing..."];
              }
              return prev;
            });
          } else if (statusData.status === "indexing") {
            setLogs(prev => {
              if (prev[prev.length - 1] !== "[INFO] Status: Building semantic index & ChromaDB vectors...") {
                return [...prev, "[INFO] Status: Building semantic index & ChromaDB vectors..."];
              }
              return prev;
            });
          } else if (statusData.status === "synthesizing_brief") {
            setLogs(prev => {
              if (prev[prev.length - 1] !== "[INFO] Status: Synthesizing structural brief via Groq 70B...") {
                return [...prev, "[INFO] Status: Synthesizing structural brief via Groq 70B..."];
              }
              return prev;
            });
          } else if (statusData.status === "brief_ready") {
            clearInterval(interval);
            setLogs(prev => [...prev, "[SUCCESS] Ingestion & Brief synthesis complete. Workspace sandbox unlocked."]);
            setStatus("brief_ready");
            fetchBrief(sid);
          } else if (statusData.status === "failed") {
            clearInterval(interval);
            setLogs(prev => [...prev, `[ERROR] Pipeline crashed: ${statusData.error}`]);
            setStatus("failed");
            setError(statusData.error);
          }
        } catch (err) {
          clearInterval(interval);
          setLogs(prev => [...prev, `[ERROR] Connection lost: ${err.message}`]);
          setStatus("failed");
        }
      }, 2000);

    } catch (err) {
      setLogs(prev => [...prev, `[ERROR] Ingest initiation failed: ${err.message}`]);
      setStatus("failed");
      setError(err.message);
    }
  };

  // Fetches the case brief from the backend
  const fetchBrief = async (sid) => {
    try {
      const res = await fetch(`${apiBase}/api/brief/${sid}`);
      if (!res.ok) throw new Error("Failed to recover case brief.");
      const data = await res.json();
      setBriefData(data);
    } catch (err) {
      console.error(err);
      setError("Failed to fetch Case Brief.");
    }
  };

  const handleUpdateBrief = (field, val, index = null, key = null) => {
    if (index !== null) {
      const updated = [...briefData[field]];
      if (key !== null) {
        updated[index][key] = val;
      } else {
        updated[index] = val;
      }
      setBriefData(prev => ({ ...prev, [field]: updated }));
    } else {
      setBriefData(prev => ({ ...prev, [field]: val }));
    }
  };

  // Saves modified brief back to the server
  const saveBriefTree = async () => {
    setIsEditingBrief(false);
    try {
      const res = await fetch(`${apiBase}/api/brief/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          brief: briefData
        })
      });
      if (!res.ok) throw new Error("Brief update rejected by schema.");
    } catch (err) {
      console.error(err);
      alert("Failed to sync brief changes: " + err.message);
    }
  };

  // Map chapter headings to the backend specs
  const getChapterSpecKey = (heading) => {
    const mappings = {
      "Opening Hook": "vignette",
      "Company Background": "company_background",
      "Industry & Competitive Context": "industry_context",
      "The Challenge": "the_challenge",
      "Root Cause Analysis": "root_cause",
      "Approach / Solution": "solution",
      "Implementation": "implementation",
      "Results and Impact": "results",
      "Key Learnings": "learnings",
      "Recommendations": "recommendations",
      "Future Scope": "future_scope",
      "Discussion Questions": "discussion_questions",
      "Process Flowchart": "process_flowchart",
      "System Diagrams": "system_diagrams",
      "Teaching Note: Learning Objectives": "learning_outcomes"
    };
    return mappings[heading] || heading;
  };

  // Streams the active chapter sequentially from the FastAPI server via SSE
  const streamChapter = async () => {
    setStatus("streaming");
    setStreamingContent("");

    try {
      const chapterKey = getChapterSpecKey(activeChapter);
      const res = await fetch(`${apiBase}/api/chapters/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          chapter_key: chapterKey,
          steerage_directive: steeragePrompt,
          custom_overview_data: customOverviewData,
          archetype: archetype,
          target_pages: targetPages
        })
      });

      if (!res.ok) throw new Error("Narrative generation failed.");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let done = false;
      let fullProse = "";

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          const chunk = decoder.decode(value, { stream: !done });
          const lines = chunk.split("\n\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const data = line.slice(6);
              if (data.startsWith("[START_STREAMING]")) {
                // stream start marker
              } else if (data.startsWith("[END_STREAMING]")) {
                // stream end marker
              } else if (data.startsWith("[ERROR]")) {
                throw new Error(data.slice(8));
              } else {
                fullProse += data;
                setStreamingContent(fullProse);
              }
            }
          }
        }
      }

      setChapters(prev => ({ ...prev, [activeChapter]: fullProse }));
      setSteeragePrompt("");
      setCustomOverviewData("");
    } catch (err) {
      console.error(err);
      alert("Streaming error: " + err.message);
    } finally {
      setStatus("brief_ready");
    }
  };

  const approveCurrentChapter = () => {
    if (!approvedChapters.includes(activeChapter)) {
      setApprovedChapters(prev => [...prev, activeChapter]);
    }
    const visibleChapters = Object.keys(chapters).filter(c => !excludedChapters.includes(c));
    const currentIndex = visibleChapters.indexOf(activeChapter);
    if (currentIndex < visibleChapters.length - 1) {
      setActiveChapter(visibleChapters[currentIndex + 1]);
    } else {
      setScreen(8);
    }
  };

  // Downloads the finalized Word volume (.docx) via the backend export endpoint
  const downloadWordFile = async (volumeType = "student") => {
    try {
      const res = await fetch(`${apiBase}/api/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          session_id: sessionId, 
          volume_type: volumeType,
          excluded_chapters: excludedChapters
        })
      });

      if (!res.ok) throw new Error("Failed to compile export file.");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const suffix = volumeType === "student" ? "student_case" : "faculty_teaching_note";
      a.download = `${companyName.toLowerCase()}_${suffix}.docx`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Download failed: " + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col selection:bg-blue-100 relative overflow-x-hidden">
      {/* Global Viewport Corporate Logo Header */}
      <header className="sticky top-0 z-50 px-4 md:px-8 py-3 flex items-center justify-between glass-nav border-b border-slate-200/80 shadow-md">
        <div className="flex items-center gap-6 md:gap-10">
          {/* Logo Frame - Takes user to project starting page (Screen 0) */}
          <button 
            type="button"
            onClick={() => handleNavClick('Home')}
            className="h-11 flex items-center cursor-pointer transition-transform hover:scale-[1.02] focus:outline-none"
          >
            <img src="/ifqm_logo_transparent.png" alt="IFQM Logo" className="h-full w-auto object-contain" />
          </button>
          
          {/* Center Navigation Links - In-App Modals & Navigation */}
          <nav className="flex items-center gap-3 md:gap-6 text-xs md:text-sm font-sans font-semibold text-slate-700">
            {IFQM_NAV_LINKS.map((link) => (
              <button
                key={link.name} 
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleNavClick(link.name);
                }}
                className="px-2.5 py-1 rounded text-slate-700 hover:text-[#2E3192] hover:bg-slate-100 cursor-pointer transition-colors font-bold"
              >
                {link.name}
              </button>
            ))}
          </nav>
        </div>
        
        {/* Right Action Block & Profile Menu */}
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex bg-emerald-50 text-emerald-800 border border-emerald-200 px-3.5 py-1.5 text-xs rounded-full items-center gap-2 font-bold shadow-sm">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse-glow"></span>
            System Live
          </div>
          
          <button 
            type="button"
            onClick={() => window.open('https://ifqm.org.in/', '_blank', 'noopener,noreferrer')}
            className="h-9 w-9 rounded-full bg-[#2E3192] text-white flex items-center justify-center font-bold text-xs shadow ring-2 ring-slate-100 cursor-pointer hover:opacity-90 transition-opacity"
          >
            EA
          </button>
        </div>
      </header>

      {/* Clean & Static Corporate Background System */}
      <div className="fixed inset-0 bg-slate-50/60 pointer-events-none z-0 overflow-hidden">
        {/* Subtle Academic Watermark Pattern */}
        <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[url('/academic_pattern.png')] bg-repeat bg-[size:400px_400px] mix-blend-multiply" />
        {/* Subtle Static Blueprint Grid Lines */}
        <div className="absolute inset-0 bg-[linear-gradient(to_right,#e2e8f0_1px,transparent_1px),linear-gradient(to_bottom,#e2e8f0_1px,transparent_1px)] bg-[size:4rem_4rem] opacity-30" />
      </div>

      {/* Main Workspace Frame */}
      <main className="flex-1 p-8 max-w-7xl w-full mx-auto flex flex-col justify-center relative z-10">
        <AnimatePresence mode="wait">
          
          {/* SCREEN 0: Clean Landing Workspace */}
          {screen === 0 && (
            <motion.div 
              key="screen0"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              className="space-y-8"
            >
              <div className="max-w-3xl space-y-4">
                <span className="text-xs font-bold text-[#2E3192] uppercase tracking-widest animate-fade-in-up">Enterprise Platform</span>
                <h2 className="text-4xl font-extrabold text-slate-950 font-sans tracking-tight animate-fade-in-up">
                  Strategic Case Analysis Workspace
                </h2>
                <p className="text-lg text-slate-600 leading-relaxed font-light animate-fade-in-up delay-100">
                  Welcome to the IFQM Case Synthesis Lab. This automated platform transforms unstructured corporate files into high-fidelity, academically structured business case studies aligning to the standards of Harvard Business School and Ivey publications.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mt-8">
                {[
                  { icon: <Building2 size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "1. Corporate Profile", desc: "Configures firm descriptors, operational boundaries, and geographical settings." },
                  { icon: <Upload size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "2. Context Ingestion", desc: "Ingests Annual Reports, financial files, and transcript recordings via Docling." },
                  { icon: <Sliders size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "3. Pre-Gen Controls", desc: "Steers case formats, archetypes, page limits, and teaching note setups." },
                  { icon: <CheckSquare size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "4. Fact Friction Audit", desc: "Resolves data anomalies and audits citations programmatically." }
                ].map((item, idx) => {
                  const delayClasses = ["delay-100", "delay-200", "delay-300", "delay-400"];
                  return (
                    <div 
                      key={idx} 
                      className={`group p-6 bg-gradient-to-b from-white to-slate-50/40 border border-slate-200/60 rounded-2xl space-y-4 shadow-[0_4px_15px_rgba(0,0,0,0.01)] transition-all duration-300 ease-out hover:-translate-y-1 hover:border-slate-300 hover:shadow-[0_20px_40px_rgba(0,0,0,0.03)] animate-fade-in-up ${delayClasses[idx]}`}
                    >
                      <div className="h-10 w-10 bg-slate-50 border border-slate-100 rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform duration-300">
                        {item.icon}
                      </div>
                      <h3 className="font-bold text-slate-950 text-base">{item.title}</h3>
                      <p className="text-xs text-slate-500 leading-relaxed">{item.desc}</p>
                    </div>
                  );
                })}
              </div>

              <div className="pt-8 border-t border-slate-100 flex justify-center animate-fade-in-up delay-300">
                <button 
                  onClick={() => setScreen(1)}
                  className="px-8 py-4 bg-slate-900 text-white font-bold rounded-xl transition-all duration-300 ease-out hover:scale-[1.02] hover:bg-[#121B2F] hover:shadow-[0_10px_30px_rgba(46,49,146,0.15)] active:scale-[0.98] flex items-center gap-3 shadow-md"
                >
                  <Play size={18} fill="white" />
                  Start Workbook
                </button>
              </div>

              {/* The Academic Lifecycle Bento Grid */}
              <div className="pt-16 border-t border-slate-100 text-center animate-fade-in-up delay-400">
                <span className="text-xs font-bold tracking-[0.2em] text-[#2E3192] uppercase">
                  The Academic Synthesis Engine
                </span>
                
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 max-w-6xl mx-auto px-2 mt-8 mb-24">
                  {[
                    { icon: <Search size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "1. Core Research", desc: "Extracts deep semantic blocks out of complex 500-page assets." },
                    { icon: <Sliders size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "2. Method Criteria", desc: "Aligns narrative parameters to global business case clearinghouses." },
                    { icon: <Database size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "3. Vector Data", desc: "Indexes structural financial and operational indicators into ChromaDB." },
                    { icon: <ShieldCheck size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "4. Empirical Evidence", desc: "Runs adversarial checking loops to guarantee zero hallucinated metrics." },
                    { icon: <FileText size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "5. Objective Prose", desc: "Drives past-tense chapter generation via NaraRouter's MiMo engine." },
                    { icon: <CheckCircle size={20} className="text-slate-600 group-hover:text-[#2E3192] transition-colors duration-300" />, title: "6. Final Conclusion", desc: "Compiles verified text elements into print-ready Word volumes." }
                  ].map((item, idx) => {
                    const staggerDelays = ["delay-100", "delay-200", "delay-300", "delay-400", "delay-500", "delay-500"];
                    return (
                      <div 
                        key={idx} 
                        className={`group p-5 bg-gradient-to-b from-white to-slate-50/40 border border-slate-200/60 rounded-2xl flex flex-col justify-between text-left shadow-[0_4px_15px_rgba(0,0,0,0.01)] transition-all duration-300 ease-out hover:-translate-y-1 hover:border-slate-300 hover:shadow-[0_20px_40px_rgba(0,0,0,0.03)] animate-fade-in-up ${staggerDelays[idx]}`}
                      >
                        <div>
                          <div className="h-10 w-10 bg-slate-50 border border-slate-100 rounded-lg flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300">
                            {item.icon}
                          </div>
                          <h4 className="font-bold text-slate-950 text-sm mb-1">{item.title}</h4>
                        </div>
                        <p className="text-[11px] text-slate-500 leading-normal mt-2">{item.desc}</p>
                      </div>
                    );
                  })}
                </div>
              </div>
            </motion.div>
          )}

          {/* SCREEN 1: Company Profile Configuration */}
          {screen === 1 && (
            <motion.div 
              key="screen1"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="max-w-2xl mx-auto space-y-8 bg-white p-8 border border-slate-200 rounded-2xl shadow-sm"
            >
              <div className="border-b border-slate-100 pb-4">
                <h3 className="text-2xl font-bold text-slate-950">Company Profile Configuration</h3>
                <p className="text-xs text-slate-500 mt-1">Specify target enterprise descriptor boundaries</p>
              </div>

              <div className="space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Corporate Name</label>
                  <input 
                    type="text" 
                    value={companyName}
                    onChange={(e) => setCompanyName(e.target.value)}
                    placeholder="e.g., Infosys, Tata Motors, Tesla"
                    className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Industry Sector</label>
                    <input 
                      type="text" 
                      value={sector}
                      onChange={(e) => setSector(e.target.value)}
                      placeholder="e.g., Technology, Manufacturing"
                      className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm"
                    />
                  </div>
                  <div className="space-y-2">
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Geographic Region</label>
                    <input 
                      type="text" 
                      value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      placeholder="e.g., South Asia, North America"
                      className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Operational Timeline Boundaries</label>
                  <input 
                    type="text" 
                    value={timeline}
                    onChange={(e) => setTimeline(e.target.value)}
                    placeholder="e.g., Fiscal Year 2021 - 2023"
                    className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm"
                  />
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex justify-between">
                <button onClick={() => setScreen(0)} className="px-6 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Back</button>
                <button 
                  onClick={() => setScreen(2)} 
                  disabled={!companyName}
                  className="px-6 py-2 bg-slate-900 text-white text-sm font-semibold rounded-lg hover:bg-slate-800 disabled:opacity-50"
                >
                  Continue
                </button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 2: Core Challenge & Context Ingestion */}
          {screen === 2 && (
            <motion.div 
              key="screen2"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="max-w-4xl mx-auto space-y-8 bg-white p-8 border border-slate-200 rounded-2xl shadow-sm"
            >
              <div className="border-b border-slate-100 pb-4">
                <h3 className="text-2xl font-bold text-slate-950">Core Challenge & Context Ingestion</h3>
                <p className="text-xs text-slate-500 mt-1">Provide unstructured case narratives and upload source documents</p>
              </div>

              <div className="space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Immediate Executive Dilemma Overview</label>
                  <textarea 
                    rows={4}
                    value={rawTextContext}
                    onChange={(e) => setRawTextContext(e.target.value)}
                    placeholder="Provide a high-level summary of the operational conflict or high-stakes administrative decision..."
                    className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm resize-none"
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  {/* Dropzone 1 */}
                  <div className="border-2 border-dashed border-slate-200 rounded-xl p-6 bg-slate-50 text-center hover:border-slate-300 transition-colors relative">
                    <input 
                      type="file" 
                      onChange={(e) => setAnnualReport(e.target.files[0])}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                    />
                    <Upload className="mx-auto text-slate-400 mb-3" size={24} />
                    <span className="text-xs font-bold text-slate-700 block mb-1">1. Annual Disclosures (PDF)</span>
                    <span className="text-[10px] text-slate-400">
                      {annualReport ? annualReport.name : "Drag & drop report files"}
                    </span>
                  </div>

                  {/* Dropzone 2 */}
                  <div className="border-2 border-dashed border-slate-200 rounded-xl p-6 bg-slate-50 text-center hover:border-slate-300 transition-colors relative">
                    <input 
                      type="file" 
                      onChange={(e) => setTranscript(e.target.files[0])}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                    />
                    <Upload className="mx-auto text-slate-400 mb-3" size={24} />
                    <span className="text-xs font-bold text-slate-700 block mb-1">2. Meeting Transcripts (PDF)</span>
                    <span className="text-[10px] text-slate-400">
                      {transcript ? transcript.name : "Drag & drop transcripts"}
                    </span>
                  </div>

                  {/* Dropzone 3 - Dummy Voice Placeholder */}
                  <div className="border-2 border-dashed border-slate-200 rounded-xl p-6 bg-slate-50 text-center hover:border-slate-300 transition-colors relative">
                    <input 
                      type="file" 
                      onChange={(e) => setVoiceRecord(e.target.files[0])}
                      className="absolute inset-0 opacity-0 cursor-pointer"
                    />
                    <Upload className="mx-auto text-slate-400 mb-3" size={24} />
                    <span className="text-xs font-bold text-slate-700 block mb-1">3. Voice Record (Audio)</span>
                    <span className="text-[10px] text-blue-500 font-semibold uppercase tracking-wider">
                      {voiceRecord ? voiceRecord.name : "[ Placeholder Dummy ]"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex justify-between">
                <button onClick={() => setScreen(1)} className="px-6 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Back</button>
                <button onClick={() => setScreen(3)} className="px-6 py-2 bg-slate-900 text-white text-sm font-semibold rounded-lg hover:bg-slate-800">Continue</button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 3: Source Verification & Scraper Settings */}
          {screen === 3 && (
            <motion.div 
              key="screen3"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="max-w-2xl mx-auto space-y-8 bg-white p-8 border border-slate-200 rounded-2xl shadow-sm"
            >
              <div className="border-b border-slate-100 pb-4">
                <h3 className="text-2xl font-bold text-slate-950">Source Verification & Scraper Settings</h3>
                <p className="text-xs text-slate-500 mt-1">Configure automated live discovery parameters</p>
              </div>

              <div className="space-y-6">
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Manual URL Target Registry</label>
                  <textarea 
                    rows={3}
                    value={manualUrls}
                    onChange={(e) => setManualUrls(e.target.value)}
                    placeholder="https://example.com/corporate-press-release-2023, https://finance.yahoo.com/news/..."
                    className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm resize-none"
                  />
                </div>

                <div className="flex items-center justify-between p-4 bg-slate-50 border border-slate-100 rounded-xl">
                  <div>
                    <span className="text-sm font-bold text-slate-950 block">Auto Web Discovery</span>
                    <span className="text-xs text-slate-500">Run search queries via DuckDuckGo to extract context fallback data</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input 
                      type="checkbox" 
                      checked={autoScrape}
                      onChange={(e) => setAutoScrape(e.target.checked)}
                      className="sr-only peer" 
                    />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-slate-900"></div>
                  </label>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex justify-between">
                <button onClick={() => setScreen(2)} className="px-6 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Back</button>
                <button onClick={() => setScreen(4)} className="px-6 py-2 bg-slate-900 text-white text-sm font-semibold rounded-lg hover:bg-slate-800">Continue</button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 4: Pre-Generation Parameter Control Matrix */}
          {screen === 4 && (
            <motion.div 
              key="screen4"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="max-w-2xl mx-auto space-y-8 bg-white p-8 border border-slate-200 rounded-2xl shadow-sm"
            >
              <div className="border-b border-slate-100 pb-4">
                <h3 className="text-2xl font-bold text-slate-950">Pre-Generation Parameter Control Matrix</h3>
                <p className="text-xs text-slate-500 mt-1">Configure layout weights and target length sliders</p>
              </div>

              <div className="space-y-8">
                {/* Case Archetype */}
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-700 uppercase tracking-wider block">Case Study Archetype</label>
                  <select 
                    value={archetype}
                    onChange={(e) => setArchetype(e.target.value)}
                    className="w-full px-4 py-3 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-sm font-semibold"
                  >
                    <option>Explanatory</option>
                    <option>Descriptive</option>
                    <option>Evaluative</option>
                    <option>Illustrative</option>
                    <option>Cumulative</option>
                  </select>
                  {(() => {
                    const descriptions = {
                      "Explanatory": "Focuses on cause-and-effect relationships to explain why events happen.",
                      "Descriptive": "Profiles a phenomenon within its real-world context using existing theories.",
                      "Evaluative": "Assesses programs or interventions to judge their overall success and effectiveness.",
                      "Illustrative": "Highlights one or two examples to make abstract concepts easy to understand.",
                      "Cumulative": "Combines past studies to build a large database of information without new research."
                    };
                    return (
                      <p className="text-[11px] text-slate-500 italic mt-1.5 pl-1">
                        👉 {descriptions[archetype] || ""}
                      </p>
                    );
                  })()}
                </div>

                {/* Target length slider */}
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">Target Page Length</label>
                    <span className="text-sm font-bold text-[#2E3192]">{targetPages} Pages (~{targetPages * 400} Words)</span>
                  </div>
                  <input 
                    type="range" 
                    min={10} 
                    max={30}
                    step={10}
                    value={targetPages}
                    onChange={(e) => setTargetPages(parseInt(e.target.value))}
                    className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-[#2E3192]"
                  />
                  <div className="flex justify-between text-[10px] text-slate-400 font-medium">
                    <span>10 Pages (Short Case)</span>
                    <span>20 Pages (Standard Case)</span>
                    <span>30 Pages (Long Case)</span>
                  </div>
                </div>

                {/* Toggle Faculty Manual */}
                <div className="flex items-center justify-between p-4 bg-slate-50 border border-slate-100 rounded-xl">
                  <div>
                    <span className="text-sm font-bold text-slate-950 block">Faculty Teaching Note</span>
                    <span className="text-xs text-slate-500">Compile parallel 10-page syllabus review instruction guides</span>
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input 
                      type="checkbox" 
                      checked={includeTeachingNote}
                      onChange={(e) => setIncludeTeachingNote(e.target.checked)}
                      className="sr-only peer" 
                    />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-slate-900"></div>
                  </label>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex justify-between">
                <button onClick={() => setScreen(3)} className="px-6 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Back</button>
                <button onClick={() => setScreen(5)} className="px-6 py-2 bg-slate-900 text-white text-sm font-semibold rounded-lg hover:bg-slate-800">Continue</button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 5: Review & Form State Confirmation */}
          {screen === 5 && (
            <motion.div 
              key="screen5"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              className="max-w-xl mx-auto space-y-8 bg-white p-8 border border-slate-200 rounded-2xl shadow-sm"
            >
              <div className="border-b border-slate-100 pb-4 text-center">
                <h3 className="text-2xl font-bold text-slate-950">Review Synthesis Setup</h3>
                <p className="text-xs text-slate-500 mt-1">Review parameters before launching processing cores</p>
              </div>

              <div className="space-y-4 bg-slate-50 p-6 rounded-xl border border-slate-100 text-sm">
                <div className="flex justify-between border-b border-slate-200/50 pb-2">
                  <span className="text-slate-500">Corporate Target:</span>
                  <span className="font-semibold text-slate-950">{companyName}</span>
                </div>
                <div className="flex justify-between border-b border-slate-200/50 pb-2">
                  <span className="text-slate-500">Industry & Sector:</span>
                  <span className="font-semibold text-slate-950">{sector || "General"} | {region || "Global"}</span>
                </div>
                <div className="flex justify-between border-b border-slate-200/50 pb-2">
                  <span className="text-slate-500">Timeline Bound:</span>
                  <span className="font-semibold text-slate-950">{timeline || "Not limited"}</span>
                </div>
                <div className="flex justify-between border-b border-slate-200/50 pb-2">
                  <span className="text-slate-500">Case Archetype:</span>
                  <span className="font-semibold text-slate-950">{archetype}</span>
                </div>
                <div className="flex justify-between border-b border-slate-200/50 pb-2">
                  <span className="text-slate-500">Target Length:</span>
                  <span className="font-semibold text-slate-950">{targetPages} Pages (~{targetPages * 500} words)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Instructor Manual:</span>
                  <span className="font-semibold text-slate-950">{includeTeachingNote ? "Yes" : "No"}</span>
                </div>
              </div>

              <div className="pt-4 border-t border-slate-100 flex justify-between">
                <button onClick={() => setScreen(4)} className="px-6 py-2 border border-slate-200 rounded-lg text-sm text-slate-600 hover:bg-slate-50">Back</button>
                <button 
                  onClick={startIngestPipeline}
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg shadow-md flex items-center gap-2"
                >
                  <Sparkles size={16} />
                  Begin Core Processing
                </button>
              </div>
            </motion.div>
          )}

          {/* SCREEN 6: Active Generation Pipeline Engine Console */}
          {screen === 6 && (
            <motion.div 
              key="screen6"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="max-w-3xl mx-auto space-y-6"
            >
              <div className="text-center space-y-2">
                <h3 className="text-2xl font-bold text-slate-950 flex items-center justify-center gap-3">
                  <RotateCw className="animate-spin text-blue-600" size={24} />
                  Executing Background Pipeline Cores
                </h3>
                <p className="text-xs text-slate-500">Docling visual OCR and ChromaDB indexing active</p>
              </div>

              {/* Console Window */}
              <div className="bg-[#0A0E17] border border-slate-800/80 rounded-2xl p-6 shadow-inner font-mono text-xs leading-relaxed text-slate-300 h-96 overflow-y-auto space-y-3">
                {logs.map((log, idx) => (
                  <div key={idx} className="flex gap-2 animate-fade-in">
                    <span className="text-slate-600">[{new Date().toLocaleTimeString()}]</span>
                    <span>{log}</span>
                  </div>
                ))}
                {status === "processing" && (
                  <div className="flex items-center gap-2 text-amber-500 font-semibold mt-2">
                    <span className="h-2 w-2 rounded-full bg-amber-500 animate-pulse-glow"></span>
                    <span>Active processing loop running...</span>
                  </div>
                )}
                <div ref={logsEndRef} />
              </div>

              {status === "brief_ready" && (
                <div className="pt-4 flex justify-center">
                  <button 
                    onClick={() => setScreen(7)} 
                    className="px-8 py-3 bg-slate-900 text-white font-bold rounded-lg hover:bg-slate-800 shadow-md flex items-center gap-2"
                  >
                    Enter Workspace Sandbox
                    <ChevronRight size={16} />
                  </button>
                </div>
              )}
            </motion.div>
          )}

          {/* SCREEN 7: Progressive Sandbox Workspace & Times New Roman Editor */}
          {screen === 7 && (
            <motion.div 
              key="screen7"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-stretch"
            >
              {/* Fact Friction Warning Modal */}
              {frictionConflict && (
                <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                  <div className="bg-white border border-slate-200 rounded-2xl max-w-2xl w-full p-8 space-y-6 shadow-2xl">
                    <div className="flex items-center gap-3 text-amber-600">
                      <AlertTriangle size={28} />
                      <h4 className="text-xl font-bold text-slate-950">Fact Friction Auditor Warning</h4>
                    </div>
                    <p className="text-xs text-slate-600 leading-relaxed">
                      Semantic analysis detected a numerical contradiction across your uploaded source files. To prevent factual degradation, select which source metadata takes priority:
                    </p>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <button 
                        onClick={() => setFrictionConflict(null)}
                        className="p-5 border border-slate-200 rounded-xl hover:border-blue-500 hover:bg-blue-50/20 text-left transition-all space-y-2"
                      >
                        <span className="text-xs font-bold text-slate-950 block">Source 1: Annual Disclosure</span>
                        <p className="text-[11px] text-slate-500 leading-relaxed">{frictionConflict.sourceA}</p>
                      </button>
                      
                      <button 
                        onClick={() => setFrictionConflict(null)}
                        className="p-5 border border-slate-200 rounded-xl hover:border-blue-500 hover:bg-blue-50/20 text-left transition-all space-y-2"
                      >
                        <span className="text-xs font-bold text-slate-950 block">Source 2: Interview Transcript</span>
                        <p className="text-[11px] text-slate-500 leading-relaxed">{frictionConflict.sourceB}</p>
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Left Column: Brief Editor, Exhibits, Control Matrix */}
              <div className="lg:col-span-5 space-y-8 flex flex-col justify-between">
                
                {/* 🧬 Pydantic Brief Tree Editor */}
                <div className="bg-gradient-to-b from-white to-slate-50/50 rounded-2xl border border-slate-200/80 shadow-[0_4px_20px_rgba(0,0,0,0.01)] hover:shadow-[0_4px_30px_rgba(0,0,0,0.02)] transition-all duration-300 p-6 space-y-4">
                  <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                    <h4 className="font-bold text-slate-950 text-sm flex items-center gap-2">
                      <Building2 size={16} className="text-[#2E3192]" />
                      Stage 3: Interactive Brief Tree Editor
                    </h4>
                    <button 
                      onClick={() => isEditingBrief ? saveBriefTree() : setIsEditingBrief(true)}
                      className="px-2.5 py-1 text-[10px] font-bold border border-slate-200 rounded-md hover:bg-slate-50 flex items-center gap-1.5 transition-colors"
                    >
                      {isEditingBrief ? <Save size={10} /> : <Edit3 size={10} />}
                      {isEditingBrief ? "Lock Tree" : "Edit Brief"}
                    </button>
                  </div>

                  {briefData && (
                    <div className="space-y-4 text-xs">
                      {/* Protagonist designation */}
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Executive Protagonist</span>
                        {isEditingBrief ? (
                          <input 
                            type="text" 
                            value={briefData.protagonist.name}
                            onChange={(e) => handleUpdateBrief("protagonist", { ...briefData.protagonist, name: e.target.value })}
                            className="w-full px-2 py-1.5 border border-slate-200 rounded focus:outline-none text-xs focus:border-[#2E3192]"
                          />
                        ) : (
                          <span className="font-semibold text-slate-900">{briefData.protagonist.name} ({briefData.protagonist.role})</span>
                        )}
                      </div>

                      {/* Dilemma description */}
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Decision Dilemma Description</span>
                        {isEditingBrief ? (
                          <textarea 
                            value={briefData.protagonist.decision}
                            onChange={(e) => handleUpdateBrief("protagonist", { ...briefData.protagonist, decision: e.target.value })}
                            className="w-full px-2 py-1.5 border border-slate-200 rounded focus:outline-none text-xs resize-none focus:border-[#2E3192]"
                            rows={2}
                          />
                        ) : (
                          <span className="text-slate-600 leading-relaxed block">{briefData.protagonist.decision}</span>
                        )}
                      </div>

                      {/* Timeline Node List */}
                      <div className="space-y-2">
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Historical Timeline Milestones</span>
                        <div className="space-y-1.5 pl-2 border-l border-slate-200">
                          {briefData.timeline.map((item, idx) => (
                            <div key={idx} className="flex gap-2 items-start p-1 hover:bg-slate-100/50 rounded transition-all active:scale-[0.99] cursor-pointer">
                              <span className="font-bold text-slate-900 shrink-0">{item.date}:</span>
                              {isEditingBrief ? (
                                <input 
                                  type="text" 
                                  value={item.event}
                                  onChange={(e) => handleUpdateBrief("timeline", e.target.value, idx, "event")}
                                  className="flex-1 px-1.5 py-0.5 border border-slate-200 rounded text-[11px] focus:outline-none focus:border-[#2E3192]"
                                />
                              ) : (
                                <span className="text-slate-600">{item.event}</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Custom Added Sections list */}
                      {customSections.length > 0 && (
                        <div className="space-y-2 pt-2 border-t border-slate-100">
                          <span className="text-[10px] font-bold text-[#2E3192] uppercase tracking-wider block">Custom Formulated Headings</span>
                          <div className="space-y-1">
                            {customSections.map((sec, idx) => (
                              <div key={idx} className="px-2 py-1 bg-blue-50/30 border border-blue-100/50 rounded text-slate-700 flex justify-between items-center animate-slide-in">
                                <span>{sec}</span>
                                <span className="text-[9px] font-bold text-[#2E3192] uppercase tracking-widest">Active</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* 📊 Spreadsheet Weaver Widget */}
                <div className="bg-gradient-to-b from-white to-slate-50/50 rounded-2xl border border-slate-200/80 shadow-[0_4px_20px_rgba(0,0,0,0.01)] hover:shadow-[0_4px_30px_rgba(0,0,0,0.02)] transition-all duration-300 p-6 space-y-4">
                  <h4 className="font-bold text-slate-950 text-sm flex items-center gap-2 border-b border-slate-100 pb-3">
                    <FileText size={16} className="text-[#2E3192]" />
                    Stage 4: Interactive Live Exhibit Weaver
                  </h4>
                  
                  <div className="overflow-hidden border border-slate-100 rounded-xl shadow-inner bg-white">
                    <table className="w-full text-[11px] text-left border-collapse">
                      <thead>
                        <tr className="border-b border-slate-200 text-slate-500 font-semibold bg-slate-50">
                          <th className="p-2.5">Metric</th>
                          <th className="p-2.5 text-center">2022</th>
                          <th className="p-2.5 text-center">2023</th>
                        </tr>
                      </thead>
                      <tbody>
                        {exhibits.map((item, idx) => (
                          <tr key={item.id} className="border-b border-slate-100 even:bg-slate-50/40 hover:bg-slate-50/80 transition-colors">
                            <td className="p-2.5 font-medium text-slate-950">{item.metric}</td>
                            <td className="p-2.5 text-center">
                              <input 
                                type="text" 
                                value={item.val2022}
                                onChange={(e) => {
                                  const updated = [...exhibits];
                                  updated[idx].val2022 = e.target.value;
                                  setExhibits(updated);
                                }}
                                className="w-14 px-1.5 py-1 border border-slate-200 focus:border-[#2E3192] rounded text-center bg-white text-slate-800 focus:outline-none transition-colors"
                              />
                            </td>
                            <td className="p-2.5 text-center">
                              <input 
                                type="text" 
                                value={item.val2023}
                                onChange={(e) => {
                                  const updated = [...exhibits];
                                  updated[idx].val2023 = e.target.value;
                                  setExhibits(updated);
                                }}
                                className="w-14 px-1.5 py-1 border border-slate-200 focus:border-[#2E3192] rounded text-center bg-white text-slate-800 focus:outline-none transition-colors"
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <span className="text-[9px] text-slate-400 block italic mt-2">Source: Processed by the author using corporate disclosures.</span>
                </div>

                {/* 📋 Active Chapters Configuration */}
                <div className="bg-gradient-to-b from-white to-slate-50/50 rounded-2xl border border-slate-200/80 shadow-[0_4px_20px_rgba(0,0,0,0.01)] p-6 space-y-3">
                  <h4 className="font-bold text-slate-950 text-sm flex items-center gap-2 border-b border-slate-100 pb-3">
                    <Check size={16} className="text-[#2E3192]" />
                    Configure Chapters to Include
                  </h4>
                  <div className="max-h-60 overflow-y-auto space-y-2 pr-1 scrollbar-thin">
                    {Object.keys(chapters).map((chapKey) => {
                      const isExcluded = excludedChapters.includes(chapKey);
                      return (
                        <label key={chapKey} className="flex items-center gap-2 text-xs font-medium text-slate-700 cursor-pointer select-none">
                          <input 
                            type="checkbox"
                            checked={!isExcluded}
                            onChange={() => {
                              if (isExcluded) {
                                setExcludedChapters(prev => prev.filter(c => c !== chapKey));
                              } else {
                                setExcludedChapters(prev => [...prev, chapKey]);
                              }
                            }}
                            className="rounded border-slate-300 text-[#2E3192] focus:ring-[#2E3192] w-3.5 h-3.5"
                          />
                          <span>{chapKey}</span>
                        </label>
                      );
                    })}
                  </div>
                  <span className="text-[10px] text-slate-400 block italic">Unchecked chapters will be hidden from tabs and skipped in Word export.</span>
                </div>

                {/* ➕ Dynamic Section & Exhibit Injector */}
                <div className="bg-gradient-to-b from-white to-slate-50/50 rounded-2xl border border-slate-200/80 shadow-[0_4px_20px_rgba(0,0,0,0.01)] hover:shadow-[0_4px_30px_rgba(0,0,0,0.02)] transition-all duration-300 p-6 space-y-4">
                  <h4 className="font-bold text-slate-950 text-sm flex items-center gap-2 border-b border-slate-100 pb-3">
                    <Sparkles size={16} className="text-[#2E3192]" />
                    Stage 5: Dynamic Section & Exhibit Injector
                  </h4>
                  
                  <div className="space-y-3">
                    <div className="space-y-1">
                      <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Heading / Title</label>
                      <input 
                        type="text" 
                        placeholder="E.g., Lean Operations, or Exhibit 3: Financial Map"
                        value={newSectionTitle}
                        onChange={(e) => setNewSectionTitle(e.target.value)}
                        className="w-full text-xs px-3 py-2 border border-slate-200 focus:border-[#2E3192] rounded-lg bg-white text-slate-800 focus:outline-none transition-colors"
                      />
                    </div>
                    
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => setNewSectionType("prose")}
                        className={`py-1.5 rounded-lg text-xs font-bold transition-all border ${
                          newSectionType === "prose"
                            ? "bg-[#2E3192]/10 border-[#2E3192] text-[#2E3192]"
                            : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        Standard Chapter
                      </button>
                      <button
                        type="button"
                        onClick={() => setNewSectionType("exhibit")}
                        className={`py-1.5 rounded-lg text-xs font-bold transition-all border ${
                          newSectionType === "exhibit"
                            ? "bg-[#2E3192]/10 border-[#2E3192] text-[#2E3192]"
                            : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                        }`}
                      >
                        Mermaid Exhibit
                      </button>
                    </div>

                    <button 
                      onClick={() => {
                        const title = newSectionTitle.trim();
                        if (!title) {
                          alert("Please enter a section or exhibit title first.");
                          return;
                        }
                        if (customSections.includes(title)) {
                          alert("This section has already been added.");
                          return;
                        }
                        
                        setChapters(prev => {
                          const keys = Object.keys(prev);
                          const updated = {};
                          let inserted = false;
                          
                          for (const key of keys) {
                            if (newSectionType === "prose" && key === "The Challenge" && !inserted) {
                              updated[key] = prev[key];
                              updated[title] = "";
                              inserted = true;
                              continue;
                            }
                            if (newSectionType === "exhibit" && key === "Teaching Note: Learning Objectives" && !inserted) {
                              updated[title] = "";
                              inserted = true;
                            }
                            updated[key] = prev[key];
                          }
                          
                          if (!inserted) {
                            updated[title] = "";
                          }
                          return updated;
                        });
                        
                        setCustomSections(prev => [...prev, title]);
                        setActiveChapter(title);
                        setNewSectionTitle("");
                      }}
                      className="w-full py-2 bg-[#2E3192] hover:bg-[#202266] text-white font-bold text-xs rounded-xl shadow-sm active:scale-[0.98] transition-all"
                    >
                      Inject Custom {newSectionType === "prose" ? "Chapter" : "Exhibit"}
                    </button>
                  </div>
                </div>

              </div>

              {/* Right Column: Narrative Editor Panel */}
              <div className="lg:col-span-7 flex flex-col justify-between bg-white border border-slate-200 rounded-2xl p-8 shadow-sm">
                
                {/* Horizontal Sequential Tabs */}
                <div className="border-b border-slate-200 pb-2 mb-6">
                  <div className="flex gap-1.5 overflow-x-auto pb-2 scrollbar-thin">
                    {Object.keys(chapters)
                      .filter(key => !excludedChapters.includes(key))
                      .map((key, idx) => (
                        <button
                          key={idx}
                          onClick={() => setActiveChapter(key)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-all ${
                            activeChapter === key 
                              ? "bg-slate-900 text-white shadow-sm" 
                              : approvedChapters.includes(key)
                                ? "bg-green-50 text-green-700 border border-green-200/50"
                                : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                          }`}
                        >
                          {approvedChapters.includes(key) && <Check size={10} className="inline mr-1" />}
                          Ch {idx + 1}: {key.split(":")[0]}
                        </button>
                      ))}
                  </div>
                </div>

                {/* 11-point Times New Roman Simulator Panel */}
                <div className="flex-1 border border-slate-200 rounded-xl p-6 min-h-[350px] max-h-[520px] overflow-y-auto bg-slate-50 mb-6 relative flex justify-center items-start shadow-inner">
                  <span className="absolute top-2.5 right-3.5 text-[9px] font-bold text-slate-400 uppercase tracking-widest font-sans z-20">Times New Roman 11pt Preview</span>
                  
                  <div className="bg-white p-10 md:p-12 border border-slate-200/80 rounded-sm shadow-[0_20px_50px_rgba(0,0,0,0.05),0_0_0_1px_rgba(0,0,0,0.01),4px_4px_0px_0px_#ffffff,5px_5px_0px_0px_#e2e8f0,9px_9px_0px_0px_#ffffff,10px_10px_0px_0px_#cbd5e1] max-w-[580px] min-h-[750px] w-full mx-auto transition-transform duration-500 hover:scale-[1.01] relative academic-preview-pane my-4 z-10">
                    <h3 className="font-bold text-center text-base uppercase tracking-tight text-slate-950 mb-6 border-b border-slate-100 pb-2">{activeChapter}</h3>
                    
                    {status === "streaming" ? (
                      <p className="leading-relaxed whitespace-pre-wrap">{streamingContent}</p>
                    ) : chapters[activeChapter] ? (
                      <p className="leading-relaxed whitespace-pre-wrap">{chapters[activeChapter]}</p>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-24 text-slate-400 space-y-3 font-sans">
                        <BookOpen size={36} className="stroke-[1.5]" />
                        <span className="text-xs">No prose generated yet. Click "Generate Section" below to start writing.</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Human-in-the-Loop Writing Steerage Controls */}
                <div className="space-y-4 border-t border-slate-100 pt-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">1. Local Steerage Directive</span>
                      <input 
                        type="text" 
                        value={steeragePrompt}
                        onChange={(e) => setSteeragePrompt(e.target.value)}
                        placeholder="e.g. Focus on financial ratios or European defect spikes..."
                        className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-xs"
                      />
                    </div>
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">2. Injected Overview / Manual Data</span>
                      <input 
                        type="text" 
                        value={customOverviewData}
                        onChange={(e) => setCustomOverviewData(e.target.value)}
                        placeholder="e.g. Append custom metrics, quotes, or plant logs..."
                        className="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500 text-xs"
                      />
                    </div>
                  </div>

                  <div className="flex justify-between items-center pt-2">
                    <div className="flex gap-2">
                      <button 
                        onClick={streamChapter}
                        disabled={status === "streaming"}
                        className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-bold text-xs rounded-lg shadow-md flex items-center gap-2 disabled:opacity-50"
                      >
                        <RefreshCw size={14} className={status === "streaming" ? "animate-spin" : ""} />
                        Generate Section
                      </button>
                    </div>

                    <button 
                      onClick={approveCurrentChapter}
                      disabled={!chapters[activeChapter] || status === "streaming"}
                      className="px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white font-bold text-xs rounded-lg shadow-md flex items-center gap-2 disabled:opacity-50"
                    >
                      <Check size={14} />
                      Approve & Continue
                    </button>
                  </div>
                </div>

              </div>
            </motion.div>
          )}

          {/* SCREEN 8: Production Export Vault */}
          {screen === 8 && (
            <motion.div 
              key="screen8"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              className="max-w-md mx-auto text-center space-y-8 bg-white p-8 border border-slate-200 rounded-2xl shadow-sm"
            >
              <div className="h-16 w-16 bg-green-50 border border-green-100 rounded-full flex items-center justify-center mx-auto text-green-500">
                <Check size={36} className="stroke-[2.5]" />
              </div>

              <div className="space-y-2">
                <h3 className="text-3xl font-extrabold text-slate-950 tracking-tight">Synthesis Complete</h3>
                <p className="text-sm text-slate-500">Your professional business case volume and teaching files have been compiled successfully.</p>
              </div>

              <div className="space-y-4 pt-4">
                {/* Export Word Button */}
                <button 
                  onClick={() => downloadWordFile("student")}
                  className="w-full py-4 bg-slate-900 text-white font-bold rounded-xl hover:bg-slate-800 transition-all flex items-center justify-center gap-3 shadow-md"
                >
                  <Download size={18} />
                  Download Case Volume (.docx)
                </button>

                {/* Export Teaching Note Button */}
                {includeTeachingNote && (
                  <button 
                    onClick={() => downloadWordFile("faculty")}
                    className="w-full py-4 border border-slate-200 text-slate-700 font-bold rounded-xl hover:bg-slate-50 transition-all flex items-center justify-center gap-3"
                  >
                    <Download size={18} />
                    Download Teaching Note (.docx)
                  </button>
                )}
              </div>

              <div className="pt-6 border-t border-slate-100">
                <button 
                  onClick={() => {
                    setScreen(0);
                    setApprovedChapters([]);
                    setChapters({
                      "Opening Hook": "",
                      "Company Background": "",
                      "Industry & Competitive Context": "",
                      "The Challenge": "",
                      "Root Cause Analysis": "",
                      "Approach / Solution": "",
                      "Implementation": "",
                      "Results and Impact": "",
                      "Key Learnings": "",
                      "Recommendations": "",
                      "Future Scope": "",
                      "Discussion Questions": "",
                      "Teaching Note: Learning Objectives": ""
                    });
                  }} 
                  className="text-xs font-bold text-blue-600 hover:underline"
                >
                  Create Another Case Study
                </button>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </main>

      {/* Official IFQM In-App Information Modal */}
      <AnimatePresence>
        {activeModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
            <motion.div 
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-xl w-full p-6 md:p-8 relative overflow-hidden space-y-5 text-slate-900"
            >
              {/* Modal Close Button */}
              <button 
                onClick={() => setActiveModal(null)}
                className="absolute top-4 right-4 h-8 w-8 rounded-full bg-slate-100 text-slate-500 hover:bg-slate-200 flex items-center justify-center font-bold text-sm transition-colors"
              >
                ✕
              </button>

              {/* Modal Header */}
              <div className="flex items-center gap-4 border-b border-slate-100 pb-4">
                <img src="/ifqm_logo_transparent.png" alt="IFQM Logo" className="h-10 w-auto object-contain" />
                <div>
                  <h3 className="text-xl font-bold text-slate-950">
                    {activeModal === 'about' && "About IFQM"}
                    {activeModal === 'offerings' && "IFQM Offerings & Programs"}
                    {activeModal === 'contact' && "Contact IFQM"}
                  </h3>
                  <p className="text-xs text-slate-500 font-medium">Indian Foundation for Quality Management</p>
                </div>
              </div>

              {/* Modal Body: About Us */}
              {activeModal === 'about' && (
                <div className="space-y-4 text-sm text-slate-600 leading-relaxed">
                  <p>
                    <strong className="text-slate-900">IFQM (Indian Foundation for Quality Management)</strong> is a Section 8, Not-for-Profit, industry-led movement dedicated to catalyzing Indian industries to become globally competitive through quality, innovation, and operational excellence.
                  </p>
                  <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4 space-y-2 text-xs">
                    <h4 className="font-bold text-[#2E3192] uppercase tracking-wider">Key Pillars & Objectives</h4>
                    <ul className="list-disc list-inside space-y-1.5 text-slate-700">
                      <li>Nation-FIRST approach to industrial competitiveness & export capability.</li>
                      <li>Adoption of world-class Total Quality Management (TQM) frameworks.</li>
                      <li>Academic synthesis of high-impact corporate case studies for leadership training.</li>
                    </ul>
                  </div>
                  <p className="text-xs text-slate-500 font-semibold">CIN: U94990KA2023NPL178280</p>
                </div>
              )}

              {/* Modal Body: Offerings */}
              {activeModal === 'offerings' && (
                <div className="space-y-4 text-sm text-slate-600">
                  <p>Explore IFQM's specialized programs designed to upgrade institutional capabilities:</p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    {[
                      { title: "Digital Courses", desc: "Executive TQM & quality engineering modules." },
                      { title: "Case Studies Lab", desc: "Harvard/Ivey standard business case study synthesis." },
                      { title: "Journey to Worldclass", desc: "Institutional mentorship for global quality compliance." },
                      { title: "Counselling & Audit", desc: "Diagnostic assessments for plant and process efficiency." }
                    ].map((item) => (
                      <div key={item.title} className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1">
                        <h5 className="font-bold text-slate-900">{item.title}</h5>
                        <p className="text-slate-500 text-[11px]">{item.desc}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Modal Body: Contact */}
              {activeModal === 'contact' && (
                <div className="space-y-4 text-sm text-slate-600">
                  <div className="space-y-3 text-xs">
                    <p className="flex items-center gap-2"><strong className="text-slate-900">Email:</strong> info@ifqm.org.in</p>
                    <p className="flex items-center gap-2"><strong className="text-slate-900">Phone:</strong> +91 78299 21433</p>
                    <div className="pt-2 border-t border-slate-100">
                      <p className="font-bold text-slate-900">Registered Office:</p>
                      <p className="text-slate-500 mt-0.5">TVR Pride, No 383, 16th Main, 3rd Block, Koramangala, Bengaluru, Karnataka 560034</p>
                    </div>
                    <div className="pt-2 border-t border-slate-100">
                      <p className="font-bold text-slate-900">Correspondence Address:</p>
                      <p className="text-slate-500 mt-0.5">25, Race Course Road, Bengaluru, Karnataka 560001</p>
                    </div>
                  </div>
                </div>
              )}

              {/* Modal Footer */}
              <div className="pt-4 border-t border-slate-100 flex justify-end">
                <button 
                  onClick={() => setActiveModal(null)}
                  className="px-5 py-2 bg-[#2E3192] text-white text-xs font-bold rounded-lg hover:bg-indigo-900 transition-colors shadow-sm"
                >
                  Close Window
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Global Viewport Corporate Footer */}
      <footer className="w-full bg-[#001833] text-slate-300 font-sans text-xs px-8 md:px-16 py-12 mt-20 border-t border-slate-800/60 z-10 relative">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-8 md:gap-12 pb-12 border-b border-slate-800/60">
          {/* Column 1 */}
          <div className="space-y-4">
            <a href="https://ifqm.org.in/" target="_blank" rel="noopener noreferrer" className="inline-block hover:opacity-90 transition-opacity">
              <img src="/ifqm_logo_transparent.png" alt="IFQM Logo" className="h-11 w-auto object-contain brightness-0 invert" />
            </a>
            <p className="leading-relaxed text-slate-400">
              A Section 8, Not-for-Profit, Industry led movement with a Nation FIRST approach to Catalyze Indian Industries to be Globally Competitive and Export capable through Quality, Innovation & Excellence.
            </p>
            <div className="text-[11px] text-slate-400 space-y-1">
              <p className="font-semibold">CIN: U94990KA2023NPL178280</p>
              <p className="flex items-center gap-1.5 mt-2">
                <span>📧</span> info@ifqm.org.in
              </p>
              <p className="flex items-center gap-1.5">
                <span>📞</span> +91 78299 21433
              </p>
            </div>
          </div>

          {/* Column 2 */}
          <div className="space-y-4">
            <h4 className="font-bold text-white text-sm tracking-wider uppercase">Our Offerings</h4>
            <ul className="space-y-2 text-slate-400">
              {[
                { label: "Events", url: "https://ifqm.org.in/" },
                { label: "Digital Courses", url: "https://ifqm.org.in/" },
                { label: "Case Studies", url: "https://ifqm.org.in/" },
                { label: "Expert Support", url: "https://ifqm.org.in/" },
                { label: "Journey to Worldclass", url: "https://ifqm.org.in/" },
                { label: "Counselling & Assessment", url: "https://ifqm.org.in/" }
              ].map((item) => (
                <li key={item.label}>
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">{item.label}</a>
                </li>
              ))}
            </ul>
          </div>

          {/* Column 3 */}
          <div className="space-y-4">
            <h4 className="font-bold text-white text-sm tracking-wider uppercase">Other Links</h4>
            <ul className="space-y-2 text-slate-400">
              {[
                { label: "Publications and News", url: "https://ifqm.org.in/" },
                { label: "IFQM search", url: "https://ifqm.org.in/" },
                { label: "Contact Us", url: "https://ifqm.org.in/" },
                { label: "About Us", url: "https://ifqm.org.in/" }
              ].map((item) => (
                <li key={item.label}>
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">{item.label}</a>
                </li>
              ))}
            </ul>
          </div>

          {/* Column 4 */}
          <div className="space-y-4">
            <h4 className="font-bold text-white text-sm tracking-wider uppercase">Connect With Us</h4>
            <div className="space-y-3 text-slate-400 leading-relaxed text-[11px]">
              <div>
                <p className="font-bold text-slate-200">Registered office:</p>
                <p>TVR Pride, No 383, 16th Main, 3rd Block, Koramangala, Bengaluru, Karnataka 560034.</p>
              </div>
              <div>
                <p className="font-bold text-slate-200">Correspondence address:</p>
                <p>25, Race Course Road, Bengaluru, Karnataka 560001.</p>
              </div>
            </div>
            {/* Social Media Row */}
            <div className="flex gap-2 pt-2">
              {[
                { tag: "ln", url: "https://www.linkedin.com/company/ifqm/" },
                { tag: "in", url: "https://ifqm.org/" },
                { tag: "yt", url: "https://www.youtube.com/@IFQM" },
                { tag: "wa", url: "https://ifqm.org/contact-us" }
              ].map((social) => (
                <a 
                  key={social.tag}
                  href={social.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="h-7 w-7 rounded-full border border-slate-700 hover:border-slate-400 hover:bg-slate-800 text-slate-300 flex items-center justify-center font-bold text-[10px] transition-all uppercase"
                >
                  {social.tag}
                </a>
              ))}
            </div>
          </div>
        </div>

        {/* Bottom Bar */}
        <div className="max-w-7xl mx-auto pt-6 flex flex-col md:flex-row justify-between items-center gap-4 text-slate-500 text-[11px]">
          <p>&copy; {new Date().getFullYear()} IFQM. All rights reserved.</p>
          <div className="flex gap-4">
            {[
              { label: "Cookie Policy", url: "https://ifqm.org/" },
              { label: "Privacy Policy", url: "https://ifqm.org/" },
              { label: "Terms & Conditions", url: "https://ifqm.org/" }
            ].map((policy) => (
              <a key={policy.label} href={policy.url} target="_blank" rel="noopener noreferrer" className="hover:text-slate-300 transition-colors">
                {policy.label}
              </a>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
