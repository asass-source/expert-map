import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { createRoot } from 'react-dom/client';

// ============================================================
// API CONFIGURATION
// ============================================================
const API_BASE = window.__API_BASE__ || '';

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, opts);
  if (!res.ok) {
    const err = await res.text().catch(() => 'Unknown error');
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

// ============================================================
// DISPLAY HELPERS
// ============================================================
function formatCurrentRole(expert) {
  const role = expert.currentRole || '';
  const company = expert.companyAffiliation || '';
  if (!role) return company || 'N/A';
  if (!company) return role;
  // If the company name is already embedded in currentRole, return as-is
  if (role.toLowerCase().includes(company.toLowerCase())) return role;
  return `${role}, ${company}`;
}

// ============================================================
// SCORING UTILITIES
// ============================================================
function calculateOverallScore(score) {
  if (!score) return 0;
  return (score.proximity || 0) * 0.25 + (score.recency || 0) * 0.20 +
         (score.relevance || 0) * 0.30 + (score.uniqueness || 0) * 0.25;
}

function getScoreLabel(overall) {
  if (overall >= 4.0) return 'High';
  if (overall >= 3.0) return 'Medium';
  return 'Low';
}

// ============================================================
// UTILITY FUNCTIONS
// ============================================================
function cn(...classes) { return classes.filter(Boolean).join(' '); }

function getScoreColor(label) {
  if (label === 'High') return 'text-teal-400 bg-teal-400/10 border-teal-400/20';
  if (label === 'Medium') return 'text-amber-400 bg-amber-400/10 border-amber-400/20';
  return 'text-gray-400 bg-gray-400/10 border-gray-400/20';
}

const nodeTypeLabels = {
  formerEmployee: 'Former Employee',
  operator: 'Industry Operator',
  competitor: 'Competitor Insider',
  supplier: 'Supply Chain Expert',
  customer: 'Customer Contact',
  analyst: 'Industry Analyst',
  regulator: 'Regulatory/Policy',
  industry_expert: 'Industry Expert'
};

const entityTypeLabels = {
  endMarket: 'End Market',
  competitor: 'Competitor',
  supplier: 'Supplier',
  customer: 'Customer',
  distributor: 'Distributor',
  regulator: 'Regulator'
};

// ============================================================
// SESSION CACHE
// ============================================================
const sessionCache = {
  companyProfiles: {},
  experts: {},
  executives: {},
  searchedTickers: [],
};

// ============================================================
// M.D. SASS LOGO (removed — using text instead)
// ============================================================

function Logo({ collapsed }) {
  return React.createElement('div', { className: 'flex items-center gap-3 px-2' },
    React.createElement('span', { className: cn('font-semibold tracking-wide text-gray-200', collapsed ? 'text-[10px]' : 'text-xs') }, 'M.D. SASS'),
    !collapsed && React.createElement('div', {
      className: 'h-6 w-px bg-white/10 mx-0.5'
    }),
    !collapsed && React.createElement('div', { className: 'text-[11px] font-medium text-gray-400 tracking-wide leading-tight' },
      'Expert', React.createElement('br'), 'Discovery'
    )
  );
}

// ============================================================
// LOADING SPINNER
// ============================================================
function LoadingSpinner({ message }) {
  return React.createElement('div', { className: 'flex flex-col items-center justify-center py-16 animate-fade-in' },
    React.createElement('div', { className: 'relative w-12 h-12 mb-4' },
      React.createElement('div', { className: 'absolute inset-0 border-2 border-teal-400/20 rounded-full' }),
      React.createElement('div', {
        className: 'absolute inset-0 border-2 border-transparent border-t-teal-400 rounded-full',
        style: { animation: 'spin 1s linear infinite' }
      })
    ),
    React.createElement('p', { className: 'text-sm text-gray-400' }, message || 'Loading...')
  );
}

// ============================================================
// SIDEBAR — two tabs
// ============================================================
const navItems = [
  { id: 'research', label: 'Company Research', icon: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z' },
  { id: 'map', label: 'Relationship Map', icon: 'M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1' },
  { id: 'guide', label: 'User Guide', icon: 'M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253' }
];

function Sidebar({ activeTab, setActiveTab, collapsed, setCollapsed }) {
  return React.createElement('aside', {
    className: cn(
      'h-full flex flex-col border-r border-white/5 bg-navy-950 transition-all duration-200',
      collapsed ? 'w-16' : 'w-56'
    )
  },
    React.createElement('div', { className: 'p-4 border-b border-white/5 flex items-center justify-between' },
      React.createElement(Logo, { collapsed }),
      !collapsed && React.createElement('button', {
        onClick: () => setCollapsed(true),
        className: 'text-gray-500 hover:text-gray-300 p-1',
        'aria-label': 'Collapse sidebar'
      },
        React.createElement('svg', { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
          React.createElement('path', { d: 'M11 19l-7-7 7-7m8 14l-7-7 7-7' })
        )
      )
    ),
    collapsed && React.createElement('button', {
      onClick: () => setCollapsed(false),
      className: 'p-4 text-gray-500 hover:text-gray-300',
      'aria-label': 'Expand sidebar'
    },
      React.createElement('svg', { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
        React.createElement('path', { d: 'M13 5l7 7-7 7M5 5l7 7-7 7' })
      )
    ),
    React.createElement('nav', { className: 'flex-1 py-3 px-2 space-y-1' },
      navItems.map(item =>
        React.createElement('button', {
          key: item.id,
          onClick: () => setActiveTab(item.id),
          className: cn(
            'w-full flex items-center gap-3 rounded-lg transition-all duration-150',
            collapsed ? 'px-3 py-3 justify-center' : 'px-3 py-2.5',
            activeTab === item.id
              ? 'bg-teal-500/10 text-teal-400'
              : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
          ),
          title: collapsed ? item.label : undefined
        },
          React.createElement('svg', { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, strokeLinecap: 'round', strokeLinejoin: 'round', className: 'shrink-0' },
            React.createElement('path', { d: item.icon })
          ),
          !collapsed && React.createElement('span', { className: 'text-sm font-medium' }, item.label)
        )
      )
    ),
    React.createElement('div', { className: 'p-3 border-t border-white/5' },
      React.createElement('a', {
        href: 'https://www.perplexity.ai/computer',
        target: '_blank',
        rel: 'noopener noreferrer',
        className: cn('text-[10px] text-gray-600 hover:text-gray-400 transition-colors', collapsed ? 'text-center block' : '')
      }, collapsed ? 'PPLX' : 'Created with Perplexity Computer')
    )
  );
}

// ============================================================
// THEME TOGGLE
// ============================================================
// ============================================================
// SEARCH COMPONENT
// ============================================================
function CompanySearch({ value, onChange, placeholder }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const ref = useRef(null);
  const debounceRef = useRef(null);

  useEffect(() => {
    if (!query || query.length < 1) { setResults([]); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const data = await apiFetch(`/api/search?q=${encodeURIComponent(query)}`);
        setResults(data);
      } catch { setResults([]); }
      setSearching(false);
    }, 500);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query]);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const selectedCompany = sessionCache.companyProfiles[value];
  const handleSelect = (ticker) => { onChange(ticker); setOpen(false); setQuery(''); };
  const showGenerateOption = query.length >= 1 && !results.some(r => r.ticker === query.toUpperCase()) && query.match(/^[A-Za-z.]{1,6}$/);

  return React.createElement('div', { ref, className: 'relative' },
    React.createElement('div', {
      className: 'flex items-center gap-2 bg-navy-950 border border-white/10 rounded-lg px-3 py-2.5 cursor-text hover:border-white/20 transition-colors',
      onClick: () => setOpen(true)
    },
      React.createElement('svg', { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, className: 'text-gray-500 shrink-0' },
        React.createElement('path', { d: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z' })
      ),
      open
        ? React.createElement('input', {
            type: 'search', autoFocus: true, value: query,
            onChange: e => setQuery(e.target.value),
            placeholder: placeholder || 'Search any public company by ticker or name...',
            className: 'bg-transparent outline-none text-sm text-white placeholder-gray-500 w-full'
          })
        : React.createElement('span', { className: cn('text-sm', selectedCompany ? 'text-white' : 'text-gray-500') },
            selectedCompany ? `${selectedCompany.ticker} — ${selectedCompany.name}` :
            (placeholder || 'Search any public company by ticker or name...')
          ),
      value && React.createElement('button', {
        onClick: (e) => { e.stopPropagation(); onChange(null); setQuery(''); },
        className: 'text-gray-500 hover:text-gray-300 p-0.5'
      },
        React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
          React.createElement('path', { d: 'M6 18L18 6M6 6l12 12' })
        )
      )
    ),
    open && React.createElement('div', {
      className: 'absolute z-50 top-full left-0 right-0 mt-1 bg-navy-950 border border-white/10 rounded-lg shadow-2xl max-h-72 overflow-y-auto scrollbar-thin'
    },
      searching && React.createElement('div', { className: 'px-4 py-3 text-sm text-gray-500 flex items-center gap-2' },
        React.createElement('div', { className: 'w-3 h-3 border border-teal-400/50 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
        'Searching...'
      ),
      !searching && query.length > 0 && results.length === 0 && !showGenerateOption &&
        React.createElement('div', { className: 'px-4 py-3 text-sm text-gray-500' }, 'No matches found. Try a different name or ticker.'),
      !searching && query.length === 0 &&
        React.createElement('div', { className: 'px-4 py-3 text-sm text-gray-500' }, 'Type a ticker (e.g. AAPL) or company name to search.'),
      !searching && results.map(c =>
        React.createElement('button', {
          key: c.ticker,
          onClick: () => handleSelect(c.ticker),
          className: cn('w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-white/5 transition-colors', c.ticker === value && 'bg-teal-500/10')
        },
          React.createElement('span', { className: 'font-mono text-xs font-medium text-teal-400 w-14' }, c.ticker),
          React.createElement('span', { className: 'text-sm text-gray-200 flex-1' }, c.name),
          React.createElement('span', { className: 'text-[11px] text-gray-500' }, c.cached ? (c.sector || 'Ready') : '')
        )
      ),
      !searching && showGenerateOption && React.createElement('button', {
        onClick: () => handleSelect(query.toUpperCase()),
        className: 'w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors border-t border-white/5'
      },
        React.createElement('span', { className: 'font-mono text-xs font-medium text-teal-400 w-14' }, query.toUpperCase()),
        React.createElement('span', { className: 'text-sm text-gray-300' }, `Generate ecosystem data for ${query.toUpperCase()}`),
        React.createElement('span', { className: 'text-[10px] px-2 py-0.5 rounded bg-teal-500/10 text-teal-400 border border-teal-500/20' }, 'AI')
      )
    )
  );
}

// ============================================================
// SCORE BADGE
// ============================================================
function ScoreBadge({ score, small }) {
  const overall = calculateOverallScore(score);
  const label = getScoreLabel(overall);
  return React.createElement('span', {
    className: cn(
      'inline-flex items-center rounded font-medium border',
      small ? 'px-1.5 py-0 text-[9px]' : 'px-2 py-0.5 text-[11px]',
      getScoreColor(label)
    )
  }, small ? overall.toFixed(1) : `${label} (${overall.toFixed(1)})`);
}

// ============================================================
// DISCLAIMER BLOCK
// ============================================================
function Disclaimer() {
  return React.createElement('div', { className: 'flex items-start gap-2 px-4 py-3 rounded-lg bg-amber-500/5 border border-amber-500/10' },
    React.createElement('svg', { className: 'w-4 h-4 text-amber-400/70 mt-0.5 flex-shrink-0', fill: 'none', viewBox: '0 0 24 24', stroke: 'currentColor', strokeWidth: 2 },
      React.createElement('path', { strokeLinecap: 'round', strokeLinejoin: 'round', d: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z' })
    ),
    React.createElement('p', { className: 'text-[10px] text-amber-200/60 leading-relaxed' },
      'Expert profiles reference real, publicly known individuals sourced via web search, SEC filings, and public records. Titles and roles may not reflect the most recent changes. Always verify current positions before outreach. This tool is for research purposes only.'
    )
  );
}

// ============================================================
// EMAIL BUTTON
// ============================================================
function EmailExpertButton({ expert, companyName }) {
  const subject = encodeURIComponent(`Expert Network Request — ${expert.name}`);
  const body = encodeURIComponent(
    `Hi,\n\n` +
    `I am conducting research on ${companyName || 'a company'} and would like to request that you add the following expert to your network for a potential consultation call:\n\n` +
    `Expert: ${expert.name}\n` +
    `Current Position: ${formatCurrentRole(expert)}\n` +
    `${expert.formerRole && expert.formerRole !== 'N/A' ? `Former Role: ${expert.formerRole}\n` : ''}` +
    `\nPlease let me know once this expert is available for scheduling.\n\n` +
    `Best regards`
  );
  const href = `mailto:?subject=${subject}&body=${body}`;
  return React.createElement('a', {
    href, target: '_blank', rel: 'noopener noreferrer',
    className: 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-medium bg-teal-500/10 text-teal-400 border border-teal-500/20 hover:bg-teal-500/20 transition-colors',
    title: `Request ${expert.name} via expert network`
  },
    React.createElement('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' },
      React.createElement('path', { d: 'M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z' }),
      React.createElement('polyline', { points: '22,6 12,13 2,6' })
    ),
    'Request'
  );
}

// ============================================================
// LINKEDIN BUTTON
// ============================================================
function LinkedInButton({ url, name, expert }) {
  // Always show a LinkedIn link — use direct URL if available, otherwise LinkedIn people search
  let href;
  const isSearch = !url || url.length <= 5;
  if (!isSearch) {
    href = url;
  } else {
    // LinkedIn people search — first name + last name only (no middle names/initials, no company)
    const rawName = (name || '').replace(/\s*\([^)]*\)/g, '').trim();
    const parts = rawName.split(/\s+/);
    // Keep only first and last name — drop middle names/initials (single letters or short tokens with periods)
    let searchName = rawName;
    if (parts.length > 2) {
      const first = parts[0];
      const last = parts[parts.length - 1];
      searchName = `${first} ${last}`;
    }
    href = `https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(searchName)}&origin=GLOBAL_SEARCH_HEADER`;
  }
  return React.createElement('a', {
    href, target: '_blank', rel: 'noopener noreferrer',
    className: 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20 hover:bg-blue-500/20 transition-colors',
    title: isSearch ? `Search LinkedIn for ${name || 'this expert'}` : 'View LinkedIn profile'
  },
    React.createElement('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'currentColor' },
      React.createElement('path', { d: 'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z' })
    ),
    'LinkedIn'
  );
}

// ============================================================
// CUSTOM HOOK: useCompanyData (two-phase: company+execs fast, experts poll in background)
// ============================================================
function useCompanyData(ticker) {
  const [company, setCompany] = useState(null);
  const [experts, setExperts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [expertsLoading, setExpertsLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    if (!ticker) { setCompany(null); setExperts([]); setExpertsLoading(false); return; }
    if (sessionCache.companyProfiles[ticker] && sessionCache.experts[ticker] && sessionCache.experts[ticker].length > 0) {
      setCompany(sessionCache.companyProfiles[ticker]);
      setExperts(sessionCache.experts[ticker]);
      setExpertsLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setExpertsLoading(false);

    // Two-phase endpoint: returns company+execs fast, experts may still be loading
    apiFetch(`/api/company-full/${encodeURIComponent(ticker)}`, { method: 'POST' })
      .then(data => {
        if (cancelled) return;
        sessionCache.companyProfiles[ticker] = data.company;
        sessionCache.executives[ticker] = data.executives;
        if (!sessionCache.searchedTickers.includes(ticker)) {
          sessionCache.searchedTickers.push(ticker);
        }
        setCompany(data.company);

        if (data.experts_loading) {
          // Experts are generating in background — poll for them
          setExperts([]);
          setLoading(false);
          setExpertsLoading(true);

          let pollInterval = null;
          let pollAttempts = 0;
          const MAX_POLL_ATTEMPTS = 90; // 3 minutes at 2s intervals
          const pollForExperts = async () => {
            pollAttempts++;
            try {
              const status = await apiFetch(`/api/experts-status/${encodeURIComponent(ticker)}`);
              if (cancelled) { clearInterval(pollInterval); return; }
              if (status.ready) {
                clearInterval(pollInterval);
                if (status.experts && status.experts.length > 0) {
                  sessionCache.experts[ticker] = status.experts;
                  setExperts(status.experts);
                } else {
                  // Generation completed but produced no experts
                  setExperts([]);
                }
                setExpertsLoading(false);
                return;
              }
              // Timeout after MAX_POLL_ATTEMPTS
              if (pollAttempts >= MAX_POLL_ATTEMPTS) {
                clearInterval(pollInterval);
                setExperts([]);
                setExpertsLoading(false);
              }
            } catch (e) {
              // Ignore poll errors, keep trying
            }
          };
          // Poll every 2 seconds
          pollInterval = setInterval(pollForExperts, 2000);
          // Also poll immediately after a short delay
          setTimeout(pollForExperts, 1000);
        } else {
          // Experts were cached — everything returned immediately
          sessionCache.experts[ticker] = data.experts;
          setExperts(data.experts);
          setLoading(false);
          setExpertsLoading(false);
        }
      }).catch(err => {
        if (cancelled) return;
        setError(err.message);
        setLoading(false);
        setExpertsLoading(false);
      });

    return () => { cancelled = true; };
  }, [ticker]);

  useEffect(() => { load(); }, [load]);

  const refreshExperts = useCallback(() => {
    if (ticker && sessionCache.experts[ticker]) {
      setExperts([...sessionCache.experts[ticker]]);
    }
  }, [ticker]);

  const refreshCompany = useCallback(() => {
    if (!ticker) return;
    // Clear session caches
    delete sessionCache.companyProfiles[ticker];
    delete sessionCache.experts[ticker];
    delete sessionCache.executives[ticker];
    if (sessionCache._formerEmployees) delete sessionCache._formerEmployees[ticker];
    setCompany(null);
    setExperts([]);
    setLoading(true);
    setError(null);
    setExpertsLoading(false);
    // Call API with refresh flag
    apiFetch(`/api/company-full/${encodeURIComponent(ticker)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh: true })
    })
      .then(data => {
        sessionCache.companyProfiles[ticker] = data.company;
        sessionCache.executives[ticker] = data.executives;
        setCompany(data.company);
        if (data.experts_loading) {
          setExperts([]);
          setLoading(false);
          setExpertsLoading(true);
          let pollAttempts = 0;
          const pollInterval = setInterval(async () => {
            pollAttempts++;
            try {
              const status = await apiFetch(`/api/experts-status/${encodeURIComponent(ticker)}`);
              if (status.ready) {
                clearInterval(pollInterval);
                sessionCache.experts[ticker] = status.experts || [];
                setExperts(status.experts || []);
                setExpertsLoading(false);
              } else if (pollAttempts >= 90) {
                clearInterval(pollInterval);
                setExperts([]);
                setExpertsLoading(false);
              }
            } catch (e) {}
          }, 2000);
        } else {
          sessionCache.experts[ticker] = data.experts;
          setExperts(data.experts);
          setLoading(false);
        }
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [ticker]);

  return { company, experts, loading, expertsLoading, error, refreshExperts, refreshCompany };
}

// ============================================================
// PREFETCH STATUS HOOK — polls server for background prefetch progress
// ============================================================
function usePrefetchStatus(ticker) {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    if (!ticker) { setStatus(null); return; }
    let cancelled = false;
    let interval = null;

    const poll = async () => {
      try {
        const data = await apiFetch(`/api/prefetch-status/${encodeURIComponent(ticker)}`);
        if (cancelled) return;
        setStatus(data);
        if (data.status === 'done' || data.status === 'none') {
          clearInterval(interval);
        }
      } catch { /* ignore */ }
    };

    // Start polling after a short delay (prefetch starts after company-full returns)
    const timeout = setTimeout(() => {
      poll();
      interval = setInterval(poll, 3000);
    }, 2000);

    return () => {
      cancelled = true;
      clearTimeout(timeout);
      if (interval) clearInterval(interval);
    };
  }, [ticker]);

  return status;
}

// ============================================================
// PREFETCH PROGRESS BAR
// ============================================================
function PrefetchBar({ status }) {
  if (!status || status.status === 'none') return null;

  const exec = status.exec_done || 0;
  const execT = status.exec_total || 0;
  const entity = status.entity_done || 0;
  const entityT = status.entity_total || 0;
  const q = status.questions_done || 0;
  const qT = status.questions_total || 0;
  const total = execT + entityT + qT;
  const done = exec + entity + q;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;
  const isDone = status.status === 'done';

  return React.createElement('div', {
    className: `rounded-lg border px-4 py-2.5 transition-all duration-500 ${isDone ? 'bg-teal-500/5 border-teal-500/20' : 'bg-white/[0.02] border-white/5'}`,
  },
    React.createElement('div', { className: 'flex items-center justify-between mb-1.5' },
      React.createElement('div', { className: 'flex items-center gap-2' },
        !isDone && React.createElement('div', { className: 'w-2 h-2 rounded-full bg-teal-400 animate-pulse' }),
        isDone && React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2.5, className: 'text-teal-400' },
          React.createElement('path', { d: 'M20 6L9 17l-5-5' })
        ),
        React.createElement('span', { className: 'text-[11px] font-medium text-gray-300' },
          isDone ? 'Background pre-loading complete — results are now instant' : 'Pre-loading experts in background...'
        )
      ),
      React.createElement('span', { className: 'text-[10px] text-gray-500 font-mono tabular-nums' }, `${done}/${total}`)
    ),
    React.createElement('div', { className: 'h-1 bg-white/5 rounded-full overflow-hidden' },
      React.createElement('div', {
        className: `h-full rounded-full transition-all duration-700 ${isDone ? 'bg-teal-500/60' : 'bg-teal-400/40'}`,
        style: { width: `${pct}%` }
      })
    ),
    !isDone && React.createElement('div', { className: 'flex gap-4 mt-1.5' },
      execT > 0 && React.createElement('span', { className: 'text-[9px] text-gray-500' }, `Executives: ${exec}/${execT}`),
      entityT > 0 && React.createElement('span', { className: 'text-[9px] text-gray-500' }, `Ecosystem: ${entity}/${entityT}`),
      qT > 0 && React.createElement('span', { className: 'text-[9px] text-gray-500' }, `Questions: ${q}/${qT}`)
    )
  );
}

// ============================================================
// ADD ENTITY BUTTON (add company to ecosystem section)
// ============================================================
function AddEntityButton({ sectionTitle, onAdd }) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState('');
  const inputRef = React.useRef(null);

  useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);

  const submit = () => {
    const v = value.trim();
    if (v) { onAdd(v); setValue(''); setOpen(false); }
  };

  if (!open) {
    return React.createElement('button', {
      onClick: () => setOpen(true),
      className: 'mt-2 inline-flex items-center gap-1 text-[10px] text-gray-500 hover:text-teal-400 transition-colors',
      title: `Add a company to ${sectionTitle}`
    },
      React.createElement('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
        React.createElement('line', { x1: 12, y1: 5, x2: 12, y2: 19 }),
        React.createElement('line', { x1: 5, y1: 12, x2: 19, y2: 12 })
      ),
      'Add'
    );
  }

  return React.createElement('div', { className: 'mt-2 flex items-center gap-1.5' },
    React.createElement('input', {
      ref: inputRef,
      type: 'text',
      value,
      onChange: (e) => setValue(e.target.value),
      onKeyDown: (e) => { if (e.key === 'Enter') submit(); if (e.key === 'Escape') { setOpen(false); setValue(''); } },
      placeholder: 'Company name...',
      className: 'w-full bg-white/5 border border-white/10 rounded px-2 py-1 text-[11px] text-white placeholder-gray-500 focus:outline-none focus:border-teal-500/40'
    }),
    React.createElement('button', {
      onClick: submit,
      className: 'shrink-0 px-2 py-1 rounded bg-teal-500/15 text-teal-400 text-[10px] font-medium hover:bg-teal-500/25 transition-colors'
    }, 'Add'),
    React.createElement('button', {
      onClick: () => { setOpen(false); setValue(''); },
      className: 'shrink-0 px-1.5 py-1 rounded text-gray-500 text-[10px] hover:text-gray-300 transition-colors'
    }, '✕')
  );
}

// ============================================================
// FIND MORE EXPERTS BUTTON
// ============================================================
function FindMoreExpertsButton({ ticker, onComplete }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleClick = async () => {
    setLoading(true);
    setResult(null);
    try {
      const data = await apiFetch(`/api/experts/${encodeURIComponent(ticker)}/more`, { method: 'POST' });
      if (data.new_experts) {
        const existing = sessionCache.experts[ticker] || [];
        sessionCache.experts[ticker] = [...existing, ...data.new_experts];
      }
      setResult(`Found ${data.new_experts?.length || 0} additional experts (${data.total} total)`);
      if (onComplete) onComplete();
    } catch (err) { setResult(`Error: ${err.message}`); }
    setLoading(false);
  };

  return React.createElement('div', { className: 'flex items-center gap-3' },
    React.createElement('button', {
      onClick: handleClick, disabled: loading,
      className: cn(
        'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
        loading ? 'bg-gray-700/50 text-gray-500 cursor-wait' : 'bg-teal-500/10 text-teal-400 border border-teal-500/20 hover:bg-teal-500/20'
      )
    },
      loading && React.createElement('div', { className: 'w-3 h-3 border border-teal-400/50 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
      React.createElement('svg', { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' },
        React.createElement('path', { d: 'M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2' }),
        React.createElement('circle', { cx: 8.5, cy: 7, r: 4 }),
        React.createElement('line', { x1: 20, y1: 8, x2: 20, y2: 14 }),
        React.createElement('line', { x1: 23, y1: 11, x2: 17, y2: 11 })
      ),
      loading ? 'Searching for more experts...' : 'Find More Experts'
    ),
    result && React.createElement('span', { className: 'text-xs text-gray-400' }, result)
  );
}

// ============================================================
// ENTITY EXPERTS PANEL (shown when clicking a company in ecosystem lists)
// ============================================================
function EntityExpertsPanel({ entityName, entityType, parentTicker, parentCompany, onClose }) {
  const [experts, setExperts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [displayName, setDisplayName] = useState(entityName);
  const [resolvedCompanies, setResolvedCompanies] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setDisplayName(entityName);
    setResolvedCompanies(null);
    apiFetch('/api/entity-experts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entityName, entityType, parentTicker })
    })
      .then(data => {
        // Handle resolved name response: { experts: [...], resolvedName: "...", resolvedCompanies: [...] }
        let expertList;
        if (data && !Array.isArray(data) && data.experts) {
          expertList = data.experts;
          if (data.resolvedName) setDisplayName(data.resolvedName);
          if (data.resolvedCompanies) setResolvedCompanies(data.resolvedCompanies);
        } else {
          expertList = data;
        }
        setExperts(expertList);
        // Register entity experts in sessionCache so bio/questions/publications work
        if (Array.isArray(expertList) && expertList.length > 0 && parentTicker) {
          const existing = sessionCache.experts[parentTicker] || [];
          for (const e of expertList) {
            if (!existing.some(ex => ex.id === e.id)) {
              existing.push(e);
            }
          }
          sessionCache.experts[parentTicker] = existing;
        }
        setLoading(false);
      })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [entityName, entityType, parentTicker]);

  return React.createElement('div', {
    className: 'fixed inset-0 z-[100] flex justify-end',
    onClick: (e) => { if (e.target === e.currentTarget) onClose(); }
  },
    React.createElement('div', { className: 'absolute inset-0 bg-black/50 backdrop-blur-sm', onClick: onClose }),
    React.createElement('div', {
      className: 'relative w-full max-w-lg bg-navy-950 border-l border-white/10 h-full overflow-y-auto scrollbar-thin shadow-2xl',
      style: { animation: 'slideInRight 0.25s ease-out' }
    },
      // Header
      React.createElement('div', { className: 'sticky top-0 bg-navy-950/95 backdrop-blur border-b border-white/5 px-6 py-4 z-10' },
        React.createElement('div', { className: 'flex items-start justify-between' },
          React.createElement('div', null,
            React.createElement('h2', { className: 'text-lg font-semibold text-white' }, displayName),
            React.createElement('p', { className: 'text-sm text-gray-400 mt-0.5' }, `${entityTypeLabels[entityType] || entityType} of ${parentCompany}`),
            resolvedCompanies && React.createElement('p', { className: 'text-[11px] text-teal-400/70 mt-1' },
              `Sourced from: ${resolvedCompanies.join(', ')}`
            )
          ),
          React.createElement('button', {
            onClick: onClose,
            className: 'p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors shrink-0'
          },
            React.createElement('svg', { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
              React.createElement('path', { d: 'M6 18L18 6M6 6l12 12' })
            )
          )
        )
      ),
      // Content
      React.createElement('div', { className: 'px-6 py-5' },
        loading && React.createElement(LoadingSpinner, { message: `Finding experts at ${displayName}...` }),
        error && React.createElement('p', { className: 'text-sm text-red-400' }, `Error: ${error}`),
        experts && experts.length === 0 && React.createElement('p', { className: 'text-sm text-gray-500' }, 'No experts found.'),
        experts && experts.length > 0 && React.createElement('div', { className: 'space-y-3' },
          React.createElement('p', { className: 'text-xs text-gray-500 uppercase tracking-wider mb-3' }, `${experts.length} Experts Found`),
          experts.map(e =>
            React.createElement('div', { key: e.id, className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
              React.createElement(ExpertName, { expert: e, className: 'text-sm font-medium text-white' }),
              e.companyAffiliation && React.createElement('div', { className: 'text-[11px] text-teal-400/80 font-medium mt-0.5' }, e.companyAffiliation),
              React.createElement('div', { className: 'text-[11px] text-gray-400 mt-0.5' }, e.currentRole || formatCurrentRole(e)),
              e.formerRole && e.formerRole !== 'N/A' && React.createElement('div', { className: 'text-[11px] text-gray-500 mt-0.5' },
                React.createElement('span', { className: 'text-gray-400' }, 'Formerly: '), e.formerRole
              ),
              React.createElement('div', { className: 'text-[11px] text-gray-300 mt-1.5' },
                React.createElement('span', { className: 'text-teal-400/80 font-medium' }, 'Connection: '), e.connectionToCompany
              ),
              React.createElement('div', { className: 'flex items-center gap-2 mt-2' },
                React.createElement(ScoreBadge, { score: e.score }),
                React.createElement(EmailExpertButton, { expert: e, companyName: parentCompany }),
                React.createElement(LinkedInButton, { url: e.linkedinUrl, name: e.name, expert: e })
              )
            )
          )
        )
      )
    )
  );
}

// ============================================================
// EXECUTIVE EXPERTS PANEL (shown when clicking an executive)
// ============================================================
function ExecExpertsPanel({ exec, ticker, companyName, onClose }) {
  const [experts, setExperts] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    apiFetch(`/api/exec-experts/${encodeURIComponent(ticker)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ execName: exec.name, execTitle: exec.title })
    })
      .then(data => {
        setExperts(data);
        // Register exec-experts in sessionCache so bio/questions/publications work
        if (Array.isArray(data) && data.length > 0 && ticker) {
          const existing = sessionCache.experts[ticker] || [];
          for (const e of data) {
            if (!existing.some(ex => ex.id === e.id)) {
              existing.push(e);
            }
          }
          sessionCache.experts[ticker] = existing;
        }
        setLoading(false);
      })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [exec.name, exec.title, ticker]);

  return React.createElement('div', {
    className: 'fixed inset-0 z-[100] flex justify-end',
    onClick: (e) => { if (e.target === e.currentTarget) onClose(); }
  },
    React.createElement('div', { className: 'absolute inset-0 bg-black/50 backdrop-blur-sm', onClick: onClose }),
    React.createElement('div', {
      className: 'relative w-full max-w-lg bg-navy-950 border-l border-white/10 h-full overflow-y-auto scrollbar-thin shadow-2xl',
      style: { animation: 'slideInRight 0.25s ease-out' }
    },
      React.createElement('div', { className: 'sticky top-0 bg-navy-950/95 backdrop-blur border-b border-white/5 px-6 py-4 z-10' },
        React.createElement('div', { className: 'flex items-start justify-between' },
          React.createElement('div', null,
            React.createElement('h2', { className: 'text-lg font-semibold text-white' }, exec.name),
            React.createElement('p', { className: 'text-sm text-gray-400 mt-0.5' }, exec.title),
            React.createElement('p', { className: 'text-xs text-gray-500 mt-1' }, `Former employees who reported to ${exec.name}`)
          ),
          React.createElement('button', {
            onClick: onClose,
            className: 'p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors shrink-0'
          },
            React.createElement('svg', { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
              React.createElement('path', { d: 'M6 18L18 6M6 6l12 12' })
            )
          )
        )
      ),
      React.createElement('div', { className: 'px-6 py-5' },
        loading && React.createElement(LoadingSpinner, { message: `Finding former reports of ${exec.name}...` }),
        error && React.createElement('p', { className: 'text-sm text-red-400' }, `Error: ${error}`),
        experts && experts.length === 0 && React.createElement('p', { className: 'text-sm text-gray-500' }, 'No experts found.'),
        experts && experts.length > 0 && React.createElement('div', { className: 'space-y-3' },
          React.createElement('p', { className: 'text-xs text-gray-500 uppercase tracking-wider mb-3' }, `${experts.length} Former Direct Reports`),
          experts.map(e =>
            React.createElement('div', { key: e.id, className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
              React.createElement(ExpertName, { expert: e, className: 'text-sm font-medium text-white' }),
              e.companyAffiliation && React.createElement('div', { className: 'text-[11px] text-teal-400/80 font-medium mt-0.5' }, e.companyAffiliation),
              React.createElement('div', { className: 'text-[11px] text-gray-400 mt-0.5' }, e.currentRole || formatCurrentRole(e)),
              e.formerRole && e.formerRole !== 'N/A' && React.createElement('div', { className: 'text-[11px] text-gray-500 mt-0.5' },
                React.createElement('span', { className: 'text-gray-400' }, 'Formerly: '), e.formerRole
              ),
              React.createElement('div', { className: 'text-[11px] text-gray-300 mt-1.5' },
                React.createElement('span', { className: 'text-teal-400/80 font-medium' }, 'Connection: '), e.connectionToCompany
              ),
              React.createElement('div', { className: 'flex items-center gap-2 mt-2' },
                React.createElement(ScoreBadge, { score: e.score }),
                React.createElement(EmailExpertButton, { expert: e, companyName }),
                React.createElement(LinkedInButton, { url: e.linkedinUrl, name: e.name, expert: e })
              )
            )
          )
        )
      )
    )
  );
}

// ============================================================
// CLICKABLE ECOSYSTEM ITEM (company name in ecosystem grid)
// ============================================================
function ClickableEntity({ name, entityType, ticker, companyName }) {
  const [showPanel, setShowPanel] = useState(false);
  return React.createElement(React.Fragment, null,
    React.createElement('button', {
      onClick: () => setShowPanel(true),
      className: 'text-xs text-gray-300 hover:text-teal-400 transition-colors cursor-pointer text-left'
    }, typeof name === 'string' ? name : String(name)),
    showPanel && React.createElement(EntityExpertsPanel, {
      entityName: typeof name === 'string' ? name : String(name),
      entityType,
      parentTicker: ticker,
      parentCompany: companyName,
      onClose: () => setShowPanel(false)
    })
  );
}

// Editable wrapper: shows edit/delete icons on hover
function EditableEntity({ name, entityType, ticker, companyName, onEdit, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState(name);
  const inputRef = React.useRef(null);

  useEffect(() => { if (editing && inputRef.current) inputRef.current.focus(); }, [editing]);

  const commitEdit = () => {
    const v = editValue.trim();
    if (v && v !== name) { onEdit(name, v); }
    setEditing(false);
  };

  if (editing) {
    return React.createElement('div', { className: 'flex items-center gap-1.5 py-0.5' },
      React.createElement('input', {
        ref: inputRef,
        type: 'text',
        value: editValue,
        onChange: (e) => setEditValue(e.target.value),
        onKeyDown: (e) => { if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') { setEditing(false); setEditValue(name); } },
        className: 'w-full bg-white/5 border border-white/10 rounded px-2 py-0.5 text-[11px] text-white placeholder-gray-500 focus:outline-none focus:border-teal-500/40'
      }),
      React.createElement('button', {
        onClick: commitEdit,
        className: 'shrink-0 text-teal-400 hover:text-teal-300 transition-colors',
        title: 'Save'
      }, React.createElement('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2.5 },
        React.createElement('polyline', { points: '20 6 9 17 4 12' })
      )),
      React.createElement('button', {
        onClick: () => { setEditing(false); setEditValue(name); },
        className: 'shrink-0 text-gray-500 hover:text-gray-300 transition-colors',
        title: 'Cancel'
      }, React.createElement('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
        React.createElement('line', { x1: 18, y1: 6, x2: 6, y2: 18 }),
        React.createElement('line', { x1: 6, y1: 6, x2: 18, y2: 18 })
      ))
    );
  }

  return React.createElement('div', { className: 'group flex items-center gap-1' },
    React.createElement(ClickableEntity, { name, entityType, ticker, companyName }),
    React.createElement('div', { className: 'opacity-0 group-hover:opacity-100 flex items-center gap-0.5 transition-opacity ml-1' },
      React.createElement('button', {
        onClick: (e) => { e.stopPropagation(); setEditing(true); setEditValue(name); },
        className: 'p-0.5 text-gray-600 hover:text-teal-400 transition-colors',
        title: 'Edit'
      }, React.createElement('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
        React.createElement('path', { d: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7' }),
        React.createElement('path', { d: 'M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z' })
      )),
      React.createElement('button', {
        onClick: (e) => { e.stopPropagation(); onDelete(name); },
        className: 'p-0.5 text-gray-600 hover:text-red-400 transition-colors',
        title: 'Remove'
      }, React.createElement('svg', { width: 10, height: 10, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
        React.createElement('line', { x1: 18, y1: 6, x2: 6, y2: 18 }),
        React.createElement('line', { x1: 6, y1: 6, x2: 18, y2: 18 })
      ))
    )
  );
}

// ============================================================
// EXECUTIVES SECTION
// ============================================================
function ExecutivesSection({ ticker, companyName }) {
  const [executives, setExecutives] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedExec, setSelectedExec] = useState(null);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    // Check session cache first
    if (sessionCache.executives[ticker]) {
      setExecutives(sessionCache.executives[ticker]);
      return;
    }
    setLoading(true);
    setError(null);
    apiFetch(`/api/executives/${encodeURIComponent(ticker)}`)
      .then(data => { setExecutives(data); sessionCache.executives[ticker] = data; setLoading(false); })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [ticker]);

  if (loading) return React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
    React.createElement('div', { className: 'flex items-center gap-3' },
      React.createElement('div', { className: 'w-4 h-4 border-2 border-teal-400/30 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
      React.createElement('span', { className: 'text-xs text-gray-400' }, 'Loading executive team...')
    )
  );
  if (error) return React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
    React.createElement('p', { className: 'text-xs text-red-400' }, `Error: ${error}`)
  );
  if (!executives || executives.length === 0) return null;

  return React.createElement(React.Fragment, null,
    React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 overflow-hidden' },
      React.createElement('button', {
        onClick: () => setIsExpanded(!isExpanded),
        className: 'w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors'
      },
        React.createElement('div', { className: 'flex items-center gap-3' },
          React.createElement('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, className: 'text-teal-400' },
            React.createElement('path', { d: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' })
          ),
          React.createElement('h3', { className: 'text-sm font-medium text-white' }, 'Executive Team'),
          React.createElement('span', { className: 'text-[11px] text-gray-500' }, `${executives.length} executives — click any to find former reports`)
        ),
        React.createElement('svg', {
          width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
          className: cn('text-gray-500 transition-transform', isExpanded && 'rotate-180')
        },
          React.createElement('path', { d: 'M19 9l-7 7-7-7' })
        )
      ),
      isExpanded && React.createElement('div', { className: 'border-t border-white/5' },
        React.createElement('div', { className: 'grid grid-cols-1 md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-white/5' },
          executives.map((exec, i) =>
            React.createElement('button', {
              key: i,
              onClick: () => setSelectedExec(exec),
              className: 'flex items-start gap-3 px-5 py-3 text-left hover:bg-white/[0.03] transition-colors group'
            },
              React.createElement('div', { className: 'w-8 h-8 rounded-full bg-teal-500/10 flex items-center justify-center shrink-0 mt-0.5' },
                React.createElement('span', { className: 'text-[11px] font-medium text-teal-400' }, exec.name.split(' ').map(n => n[0]).join('').slice(0, 2))
              ),
              React.createElement('div', { className: 'min-w-0' },
                React.createElement('div', { className: 'text-xs font-medium text-white group-hover:text-teal-400 transition-colors' }, exec.name),
                React.createElement('div', { className: 'text-[10px] text-gray-400 truncate' }, exec.title),
                React.createElement('div', { className: 'text-[10px] text-gray-600 mt-0.5 truncate' }, exec.description)
              )
            )
          )
        )
      )
    ),
    selectedExec && React.createElement(ExecExpertsPanel, {
      exec: selectedExec,
      ticker,
      companyName,
      onClose: () => setSelectedExec(null)
    })
  );
}

// ============================================================
// FORMER EMPLOYEES SECTION
// ============================================================
function FormerEmployeesSection({ ticker, companyName }) {
  const [employees, setEmployees] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    // Check session cache
    if (sessionCache._formerEmployees && sessionCache._formerEmployees[ticker]) {
      setEmployees(sessionCache._formerEmployees[ticker]);
      return;
    }
    setLoading(true);
    setError(null);
    apiFetch(`/api/former-employees/${encodeURIComponent(ticker)}`)
      .then(data => {
        setEmployees(data);
        if (!sessionCache._formerEmployees) sessionCache._formerEmployees = {};
        sessionCache._formerEmployees[ticker] = data;
        // Also register in experts cache so bio/questions work
        if (Array.isArray(data) && data.length > 0 && ticker) {
          const existing = sessionCache.experts[ticker] || [];
          for (const e of data) {
            if (!existing.some(ex => ex.id === e.id)) {
              existing.push(e);
            }
          }
          sessionCache.experts[ticker] = existing;
        }
        setLoading(false);
      })
      .catch(err => { setError(err.message); setLoading(false); });
  }, [ticker]);

  if (loading) return React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
    React.createElement('div', { className: 'flex items-center gap-3' },
      React.createElement('div', { className: 'w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
      React.createElement('span', { className: 'text-xs text-gray-400' }, 'Finding former senior employees...')
    )
  );
  if (error) return React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
    React.createElement('p', { className: 'text-xs text-red-400' }, `Error: ${error}`)
  );
  if (!employees || employees.length === 0) return null;

  // Group by level
  const levelOrder = ['C-Suite', 'SVP', 'VP', 'Managing Director'];
  const grouped = {};
  for (const emp of employees) {
    const lvl = emp.level || 'VP';
    if (!grouped[lvl]) grouped[lvl] = [];
    grouped[lvl].push(emp);
  }

  const levelColors = {
    'C-Suite': 'text-amber-400',
    'SVP': 'text-orange-400',
    'VP': 'text-teal-400',
    'Managing Director': 'text-blue-400'
  };

  return React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 overflow-hidden' },
    React.createElement('button', {
      onClick: () => setIsExpanded(!isExpanded),
      className: 'w-full flex items-center justify-between px-5 py-4 hover:bg-white/[0.02] transition-colors'
    },
      React.createElement('div', { className: 'flex items-center gap-3' },
        React.createElement('svg', { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.5, className: 'text-amber-400' },
          React.createElement('path', { d: 'M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z' })
        ),
        React.createElement('h3', { className: 'text-sm font-medium text-white' }, 'Former Employees'),
        React.createElement('span', { className: 'text-[11px] text-gray-500' }, `${employees.length} former C-Suite, SVP, VP & MD professionals`)
      ),
      React.createElement('svg', {
        width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
        className: cn('text-gray-500 transition-transform', isExpanded && 'rotate-180')
      },
        React.createElement('path', { d: 'M19 9l-7 7-7-7' })
      )
    ),
    isExpanded && React.createElement('div', { className: 'border-t border-white/5 px-5 py-4 space-y-4' },
      levelOrder.filter(lvl => grouped[lvl] && grouped[lvl].length > 0).map(lvl =>
        React.createElement('div', { key: lvl },
          React.createElement('div', { className: 'flex items-center gap-2 mb-2' },
            React.createElement('span', { className: cn('text-[10px] font-semibold uppercase tracking-wider', levelColors[lvl] || 'text-gray-400') }, lvl),
            React.createElement('span', { className: 'text-[10px] text-gray-600' }, `(${grouped[lvl].length})`)
          ),
          React.createElement('div', { className: 'grid grid-cols-1 md:grid-cols-2 gap-2' },
            grouped[lvl].map(emp =>
              React.createElement('div', {
                key: emp.id,
                className: 'bg-white/[0.02] rounded-lg border border-white/5 p-3 hover:bg-white/[0.04] transition-colors'
              },
                React.createElement('div', { className: 'flex items-start justify-between gap-2' },
                  React.createElement('div', { className: 'min-w-0 flex-1' },
                    React.createElement(ExpertName, { expert: emp, className: 'text-xs font-medium text-white' }),
                    React.createElement('div', { className: 'text-[10px] text-gray-400 mt-0.5 truncate' }, formatCurrentRole(emp)),
                    emp.formerRole && emp.formerRole !== 'N/A' && React.createElement('div', { className: 'text-[10px] text-gray-500 mt-0.5 truncate' },
                      React.createElement('span', { className: 'text-amber-400/60' }, 'Previously: '), emp.formerRole
                    ),
                    emp.yearsAtCompany && React.createElement('div', { className: 'text-[10px] text-gray-600 mt-0.5' }, emp.yearsAtCompany),
                    emp.connectionToCompany && React.createElement('div', { className: 'text-[10px] text-gray-300 mt-1' },
                      emp.connectionToCompany
                    )
                  )
                ),
                React.createElement('div', { className: 'flex items-center gap-1.5 mt-2' },
                  React.createElement(EmailExpertButton, { expert: emp, companyName }),
                  React.createElement(LinkedInButton, { url: emp.linkedinUrl, name: emp.name, expert: emp }),
                  (emp.expertise || []).length > 0 && React.createElement('div', { className: 'flex gap-1 ml-1' },
                    emp.expertise.slice(0, 2).map((ex, j) =>
                      React.createElement('span', { key: j, className: 'text-[8px] px-1.5 py-0.5 rounded bg-white/5 text-gray-500' }, ex)
                    )
                  )
                )
              )
            )
          )
        )
      )
    )
  );
}

// ============================================================
// SCREEN 1: COMPANY RESEARCH
// ============================================================
function CompanyResearch({ onCompanyLoaded, ticker, setTicker }) {
  const { company, loading, error, refreshCompany } = useCompanyData(ticker);
  const prefetchSt = usePrefetchStatus(ticker);
  const [addedEntities, setAddedEntities] = useState({});  // { sectionKey: [name, ...] }
  const [editedEntities, setEditedEntities] = useState({}); // { sectionKey: { oldName: newName, ... } }
  const [deletedEntities, setDeletedEntities] = useState({}); // { sectionKey: [name, ...] }

  // Former Employees state
  const [formerEmployees, setFormerEmployees] = useState([]);
  const [formerLoading, setFormerLoading] = useState(false);
  const [formerRefreshKey, setFormerRefreshKey] = useState(0);

  // Reset all entity overrides when company changes
  useEffect(() => { setAddedEntities({}); setEditedEntities({}); setDeletedEntities({}); }, [ticker]);

  // Fetch former employees when company loads (or on refresh)
  useEffect(() => {
    if (!ticker) return;
    if (formerRefreshKey === 0 && sessionCache._formerEmployees && sessionCache._formerEmployees[ticker]) {
      setFormerEmployees(sessionCache._formerEmployees[ticker]);
      return;
    }
    setFormerLoading(true);
    setFormerEmployees([]);
    apiFetch(`/api/former-employees/${encodeURIComponent(ticker)}`)
      .then(data => {
        setFormerEmployees(data || []);
        if (!sessionCache._formerEmployees) sessionCache._formerEmployees = {};
        sessionCache._formerEmployees[ticker] = data || [];
        // Register in experts cache so bio/questions work
        if (Array.isArray(data) && data.length > 0) {
          const existing = sessionCache.experts[ticker] || [];
          for (const e of data) {
            if (!existing.some(ex => ex.id === e.id)) existing.push(e);
          }
          sessionCache.experts[ticker] = existing;
        }
        setFormerLoading(false);
      })
      .catch(() => { setFormerLoading(false); });
  }, [ticker, formerRefreshKey]);

  const handleAddEntity = (sectionKey, name) => {
    setAddedEntities(prev => ({
      ...prev,
      [sectionKey]: [...(prev[sectionKey] || []), name]
    }));
  };

  const handleEditEntity = (sectionKey, oldName, newName) => {
    setEditedEntities(prev => {
      const sectionEdits = { ...(prev[sectionKey] || {}) };
      // Find the original key that maps to oldName (for chained edits)
      const originalKey = Object.keys(sectionEdits).find(k => sectionEdits[k] === oldName);
      if (originalKey) {
        sectionEdits[originalKey] = newName; // Update original→final mapping
      } else {
        sectionEdits[oldName] = newName;
      }
      return { ...prev, [sectionKey]: sectionEdits };
    });
  };

  const handleDeleteEntity = (sectionKey, name) => {
    setDeletedEntities(prev => {
      const existing = prev[sectionKey] || [];
      if (existing.includes(name)) return prev;
      return { ...prev, [sectionKey]: [...existing, name] };
    });
  };

  // Notify parent when company is loaded (for relationship map sync)
  useEffect(() => {
    if (company && onCompanyLoaded) {
      onCompanyLoaded(company);
    }
  }, [company, onCompanyLoaded]);



  if (!ticker) {
    return React.createElement('div', { className: 'flex flex-col items-center justify-center h-full px-8' },
      React.createElement('div', { className: 'w-full max-w-lg' },
        React.createElement('p', { className: 'text-sm text-gray-400 mb-6 text-center' }, 'Search any public company to explore its ecosystem and discover relevant experts.'),
        React.createElement(CompanySearch, { value: ticker, onChange: setTicker }),
        React.createElement('div', { className: 'mt-8 text-center' },
          React.createElement('p', { className: 'text-xs text-gray-600' }, 'Enter any ticker symbol (e.g. AAPL, NVDA, DAL) or company name to get started.')
        )
      )
    );
  }

  if (loading) {
    return React.createElement(LoadingSpinner, { message: `Generating ecosystem analysis for ${ticker}... This may take 30-60 seconds.` });
  }

  if (error) {
    return React.createElement('div', { className: 'flex flex-col items-center justify-center h-full px-8' },
      React.createElement('div', { className: 'text-center' },
        React.createElement('p', { className: 'text-red-400 text-sm mb-4' }, `Error: ${error}`),
        React.createElement('button', { onClick: () => setTicker(null), className: 'text-teal-400 hover:text-teal-300 text-sm' }, 'Go back')
      )
    );
  }

  if (!company) return null;

  // Ecosystem section config with entity types for clickability
  const ecosystemSections = [
    { title: 'End Markets', items: company.endMarkets, color: 'text-teal-400', entityType: 'endMarket' },
    { title: 'Competitors', items: company.competitors, color: 'text-red-400', entityType: 'competitor' },
    { title: 'Suppliers', items: company.suppliers, color: 'text-blue-400', entityType: 'supplier' },
    { title: 'Customers', items: company.customers, color: 'text-yellow-400', entityType: 'customer' },
    { title: 'Distributors', items: company.distributors, color: 'text-emerald-400', entityType: 'distributor' },
    { title: 'Regulators', items: company.regulators, color: 'text-purple-400', entityType: 'regulator' }
  ];

  return React.createElement('div', { className: 'space-y-6 animate-fade-in' },
    // Header
    React.createElement('div', { className: 'flex items-start justify-between' },
      React.createElement('div', null,
        React.createElement('div', { className: 'flex items-center gap-3 mb-1' },
          React.createElement('span', { className: 'font-mono text-lg text-teal-400 font-semibold' }, company.ticker),
          React.createElement('span', { className: 'text-xs px-2 py-0.5 rounded bg-white/5 text-gray-400' }, company.sector)
        ),
        React.createElement('h1', { className: 'text-xl font-semibold text-white' }, company.name)
      ),
      React.createElement('div', { className: 'flex items-center gap-3' },
        React.createElement('button', {
          onClick: () => { refreshCompany(); setFormerRefreshKey(k => k + 1); },
          className: 'flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-400 hover:text-teal-400 bg-white/5 hover:bg-white/10 rounded-lg border border-white/5 transition-colors',
          title: 'Regenerate company profile and experts from scratch'
        },
          React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' },
            React.createElement('path', { d: 'M21.5 2v6h-6' }),
            React.createElement('path', { d: 'M2.5 22v-6h6' }),
            React.createElement('path', { d: 'M2 11.5a10 10 0 0 1 18.8-4.3' }),
            React.createElement('path', { d: 'M22 12.5a10 10 0 0 1-18.8 4.2' })
          ),
          'Refresh'
        ),
        React.createElement('div', { className: 'w-72' },
          React.createElement(CompanySearch, { value: ticker, onChange: setTicker, placeholder: 'Switch company...' })
        )
      )
    ),

    // Background Prefetch Progress
    React.createElement(PrefetchBar, { status: prefetchSt }),

    // Business Summary
    React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 p-5' },
      React.createElement('h3', { className: 'text-xs font-medium text-gray-400 uppercase tracking-wider mb-2' }, 'Business Model'),
      React.createElement('p', { className: 'text-sm text-gray-300 leading-relaxed' }, company.businessModelSummary)
    ),

    // Executives Section
    React.createElement(ExecutivesSection, { ticker: company.ticker, companyName: company.name }),

    // Ecosystem Grid — editable items with add/edit/delete
    React.createElement('div', { className: 'grid grid-cols-2 xl:grid-cols-3 gap-4' },
      ecosystemSections.map(section => {
        const extra = addedEntities[section.entityType] || [];
        const edits = editedEntities[section.entityType] || {};
        const deleted = deletedEntities[section.entityType] || [];
        const rawItems = [...(section.items || []), ...extra];
        // Apply edits and filter deletes
        const allItems = rawItems
          .map(item => edits[item] || item)
          .filter(item => !deleted.includes(item));
        return React.createElement('div', { key: section.title, className: 'bg-white/[0.03] rounded-xl border border-white/5 p-4' },
          React.createElement('h4', { className: cn('text-[11px] font-medium uppercase tracking-wider mb-2', section.color) }, section.title),
          React.createElement('div', { className: 'space-y-1' },
            allItems.map((item, i) =>
              React.createElement('div', { key: `${item}-${i}` },
                React.createElement(EditableEntity, {
                  name: item,
                  entityType: section.entityType,
                  ticker: company.ticker,
                  companyName: company.name,
                  onEdit: (oldName, newName) => handleEditEntity(section.entityType, oldName, newName),
                  onDelete: (name) => handleDeleteEntity(section.entityType, name)
                })
              )
            )
          ),
          React.createElement(AddEntityButton, {
            sectionTitle: section.title,
            onAdd: (name) => handleAddEntity(section.entityType, name)
          })
        );
      })
    ),

    // Disclaimer
    React.createElement(Disclaimer),

    // Former Employees Table
    React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 overflow-hidden' },
      React.createElement('div', { className: 'px-5 py-4 border-b border-white/5 flex items-center justify-between' },
        React.createElement('h3', { className: 'text-xs font-medium text-gray-400 uppercase tracking-wider' },
          formerLoading ? 'Former Employees — Searching...' : `Former Employees — ${formerEmployees.length} Results`
        )
      ),
      formerLoading
        ? React.createElement('div', { className: 'flex flex-col items-center justify-center py-12' },
            React.createElement('div', { className: 'animate-spin h-6 w-6 border-2 border-amber-400/30 border-t-amber-400 rounded-full mb-3' }),
            React.createElement('p', { className: 'text-xs text-gray-400' }, 'Finding former C-Suite, SVP, VP & MD employees...'),
            React.createElement('p', { className: 'text-[10px] text-gray-600 mt-1' }, 'Searching public records and verifying identities.')
          )
        : formerEmployees.length === 0
          ? React.createElement('div', { className: 'flex flex-col items-center justify-center py-12' },
              React.createElement('p', { className: 'text-sm text-gray-400' }, 'No former employees found for this company.'),
              React.createElement('p', { className: 'text-xs text-gray-500 mt-1' }, 'Try refreshing the company to search again.')
            )
          : React.createElement('div', { className: 'overflow-x-auto' },
        React.createElement('table', { className: 'w-full text-left' },
          React.createElement('thead', null,
            React.createElement('tr', { className: 'border-b border-white/5' },
              ['Name', 'Current Company', 'Current Role', 'Former Role', 'Level', 'Tenure', 'Expertise', 'Connection', 'Actions'].map(h =>
                React.createElement('th', { key: h, className: 'px-4 py-2.5 text-[10px] font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap' }, h)
              )
            )
          ),
          React.createElement('tbody', null,
            formerEmployees.map(e =>
              React.createElement('tr', { key: e.id, className: 'border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors' },
                React.createElement('td', { className: 'px-4 py-2.5 text-xs font-medium whitespace-nowrap' }, React.createElement(ExpertName, { expert: e, className: 'text-white text-xs font-medium' })),
                React.createElement('td', { className: 'px-4 py-2.5 text-[11px] text-teal-400/80 max-w-[160px] truncate' }, e.companyAffiliation || ''),
                React.createElement('td', { className: 'px-4 py-2.5 text-[11px] text-gray-300 max-w-[200px] truncate' }, e.currentRole || ''),
                React.createElement('td', { className: 'px-4 py-2.5 text-[11px] text-gray-400 max-w-[180px] truncate' }, e.formerRole || ''),
                React.createElement('td', { className: 'px-4 py-2.5' },
                  React.createElement('span', { className: cn('text-[10px] px-2 py-0.5 rounded-full font-medium',
                    e.level === 'C-Suite' ? 'bg-amber-500/10 text-amber-400' :
                    e.level === 'SVP' ? 'bg-orange-500/10 text-orange-400' :
                    e.level === 'VP' ? 'bg-teal-500/10 text-teal-400' :
                    'bg-blue-500/10 text-blue-400'
                  ) }, e.level || 'VP')
                ),
                React.createElement('td', { className: 'px-4 py-2.5 text-[11px] text-gray-400 whitespace-nowrap' }, e.yearsAtCompany || ''),
                React.createElement('td', { className: 'px-4 py-2.5' },
                  React.createElement('div', { className: 'flex gap-1 flex-wrap' },
                    (e.expertise || []).slice(0, 2).map((ex, j) =>
                      React.createElement('span', { key: j, className: 'text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-gray-400' }, ex)
                    )
                  )
                ),
                React.createElement('td', { className: 'px-4 py-2.5 text-[11px] text-gray-400 max-w-[200px]' },
                  React.createElement('span', { className: 'line-clamp-2' }, e.connectionToCompany)
                ),
                React.createElement('td', { className: 'px-4 py-2.5' },
                  React.createElement('div', { className: 'flex items-center gap-1' },
                    React.createElement(EmailExpertButton, { expert: e, companyName: company.name }),
                    React.createElement(LinkedInButton, { url: e.linkedinUrl, name: e.name, expert: e })
                  )
                )
              )
            )
          )
        )
      )
    )
  );
}

// ============================================================
// EXPERT DETAIL PANEL (slide-over bio view)
// ============================================================
const ExpertPanelContext = React.createContext({ openExpert: () => {} });

// Publication type icons (SVG paths)
const PUB_TYPE_ICONS = {
  article: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z',
  white_paper: 'M14 2H6c-1.1 0-2 .9-2 2v16c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z',
  blog_post: 'M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04c.39-.39.39-1.02 0-1.41l-2.34-2.34c-.39-.39-1.02-.39-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z',
  interview: 'M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z',
  podcast: 'M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z',
  conference: 'M21 3H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H3V5h18v14zM10 8H5v2h5V8zm9 0h-5v2h5V8zm-9 4H5v2h5v-2zm9 0h-5v2h5v-2z',
  report: 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z',
  other: 'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z'
};

const PUB_TYPE_LABELS = {
  article: 'Article',
  white_paper: 'White Paper',
  blog_post: 'Blog Post',
  interview: 'Interview',
  podcast: 'Podcast',
  conference: 'Conference',
  report: 'Report',
  other: 'Publication'
};

function ExpertDetailPanel({ expert, onClose }) {
  const [questions, setQuestions] = useState(null);
  const [loadingQ, setLoadingQ] = useState(false);
  const [publications, setPublications] = useState(null);
  const [loadingPubs, setLoadingPubs] = useState(false);
  const [topicExperts, setTopicExperts] = useState(null);  // { topic, experts, loading, error }
  const { openExpert } = React.useContext(ExpertPanelContext);

  const ticker = Object.keys(sessionCache.experts).find(t =>
    (sessionCache.experts[t] || []).some(e => e.id === expert.id)
  );
  const companyName = sessionCache.companyProfiles[ticker]?.name || '';

  const loadQuestions = async () => {
    if (questions) return;
    if (!ticker) return;
    setLoadingQ(true);
    try {
      const data = await apiFetch(`/api/experts/${encodeURIComponent(ticker)}/${expert.id}/questions`);
      setQuestions(data);
    } catch (err) { setQuestions([`Failed to load: ${err.message}`]); }
    setLoadingQ(false);
  };

  // Auto-fetch publications when panel opens
  useEffect(() => {
    const fetchPubs = async () => {
      setLoadingPubs(true);
      try {
        const data = await apiFetch('/api/expert-publications', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: expert.name,
            affiliation: expert.companyAffiliation || ''
          })
        });
        setPublications(data);
      } catch (err) {
        console.error('Publications fetch error:', err);
        setPublications([]);
      }
      setLoadingPubs(false);
    };
    fetchPubs();
  }, [expert.name, expert.companyAffiliation]);

  const searchExpertsByTopic = async (topic) => {
    if (topicExperts?.topic === topic && !topicExperts?.error) return; // Already loaded
    setTopicExperts({ topic, experts: [], loading: true, error: null });
    try {
      const data = await apiFetch('/api/expertise-experts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, parentTicker: ticker })
      });
      setTopicExperts({ topic, experts: data, loading: false, error: null });
      // Register new experts in sessionCache
      if (ticker && data.length) {
        const existing = sessionCache.experts[ticker] || [];
        data.forEach(e => {
          if (!existing.some(ex => ex.id === e.id)) existing.push(e);
        });
        sessionCache.experts[ticker] = existing;
      }
    } catch (err) {
      setTopicExperts({ topic, experts: [], loading: false, error: err.message });
    }
  };

  return React.createElement('div', {
    className: 'fixed inset-0 z-[100] flex justify-end',
    onClick: (e) => { if (e.target === e.currentTarget) onClose(); }
  },
    React.createElement('div', { className: 'absolute inset-0 bg-black/50 backdrop-blur-sm', onClick: onClose }),
    React.createElement('div', {
      className: 'relative w-full max-w-lg bg-navy-950 border-l border-white/10 h-full overflow-y-auto scrollbar-thin shadow-2xl',
      style: { animation: 'slideInRight 0.25s ease-out' }
    },
      // Header
      React.createElement('div', { className: 'sticky top-0 bg-navy-950/95 backdrop-blur border-b border-white/5 px-6 py-4 z-10' },
        React.createElement('div', { className: 'flex items-start justify-between' },
          React.createElement('div', { className: 'flex-1 min-w-0 pr-4' },
            React.createElement('h2', { className: 'text-lg font-semibold text-white truncate' }, expert.name),
            expert.companyAffiliation && React.createElement('p', { className: 'text-sm text-teal-400/80 mt-0.5 truncate font-medium' }, expert.companyAffiliation),
            React.createElement('p', { className: 'text-sm text-gray-400 mt-0.5 truncate' }, expert.currentRole || formatCurrentRole(expert))
          ),
          React.createElement('button', {
            onClick: onClose,
            className: 'p-1.5 rounded-lg text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors shrink-0'
          },
            React.createElement('svg', { width: 20, height: 20, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
              React.createElement('path', { d: 'M6 18L18 6M6 6l12 12' })
            )
          )
        ),
        React.createElement('div', { className: 'flex items-center gap-3 mt-3 flex-wrap' },
          React.createElement(ScoreBadge, { score: expert.score }),
          React.createElement('span', { className: 'text-[10px] px-2 py-0.5 rounded bg-white/5 text-gray-400 capitalize' },
            nodeTypeLabels[expert.ecosystemNode] || expert.ecosystemNode
          ),
          React.createElement('span', { className: 'text-[10px] text-gray-500 font-mono' }, `${expert.yearsExperience}y experience`)
        ),
        React.createElement('div', { className: 'flex items-center gap-2 mt-3' },
          React.createElement(EmailExpertButton, { expert, companyName }),
          React.createElement(LinkedInButton, { url: expert.linkedinUrl, name: expert.name, expert })
        )
      ),
      // Body
      React.createElement('div', { className: 'px-6 py-5 space-y-5' },
        // Relevant Experience
        React.createElement('div', null,
          React.createElement('h4', { className: 'text-[10px] text-gray-500 uppercase tracking-wider mb-2' }, 'Relevant Experience'),
          React.createElement('div', { className: 'bg-white/[0.03] rounded-lg border border-white/5 p-3 space-y-2' },
            React.createElement('div', { className: 'flex items-start gap-2' },
              React.createElement('span', { className: 'text-[10px] text-gray-500 shrink-0 w-16 uppercase mt-0.5' }, 'Company'),
              React.createElement('span', { className: 'text-[13px] text-teal-400/90 font-medium' }, expert.companyAffiliation || 'Not specified')
            ),
            React.createElement('div', { className: 'flex items-start gap-2' },
              React.createElement('span', { className: 'text-[10px] text-gray-500 shrink-0 w-16 uppercase mt-0.5' }, 'Current'),
              React.createElement('span', { className: 'text-[13px] text-gray-200' }, expert.currentRole || formatCurrentRole(expert))
            ),
            expert.formerRole && expert.formerRole !== 'N/A' && React.createElement('div', { className: 'flex items-start gap-2' },
              React.createElement('span', { className: 'text-[10px] text-gray-500 shrink-0 w-16 uppercase mt-0.5' }, 'Former'),
              React.createElement('span', { className: 'text-[13px] text-gray-300' }, expert.formerRole)
            ),
            React.createElement('div', { className: 'flex items-start gap-2' },
              React.createElement('span', { className: 'text-[10px] text-gray-500 shrink-0 w-16 uppercase mt-0.5' }, 'Years'),
              React.createElement('span', { className: 'text-[13px] text-gray-300 font-mono' }, `${expert.yearsExperience} years`)
            )
          )
        ),
        // Connection to Company
        React.createElement('div', null,
          React.createElement('h4', { className: 'text-[10px] text-gray-500 uppercase tracking-wider mb-2' }, `Connection to ${companyName || 'Company'}`),
          React.createElement('p', { className: 'text-sm text-gray-300 leading-relaxed' }, expert.connectionToCompany)
        ),
        // Publications section
        React.createElement('div', null,
          React.createElement('h4', { className: 'text-[10px] text-gray-500 uppercase tracking-wider mb-2' }, 'Published Content'),
          loadingPubs && React.createElement('div', { className: 'flex items-center gap-2 py-3' },
            React.createElement('div', { className: 'w-3 h-3 border border-teal-400/50 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
            React.createElement('span', { className: 'text-xs text-gray-500' }, 'Searching for articles, white papers, and publications...')
          ),
          publications && publications.length > 0 && React.createElement('div', {
            className: 'bg-white/[0.03] rounded-lg border border-white/5 divide-y divide-white/5 overflow-hidden'
          },
            publications.map((pub, i) =>
              React.createElement('a', {
                key: i,
                href: pub.url,
                target: '_blank',
                rel: 'noopener noreferrer',
                className: 'flex items-start gap-3 px-3 py-2.5 hover:bg-white/[0.04] transition-colors group'
              },
                React.createElement('div', { className: 'shrink-0 mt-0.5' },
                  React.createElement('svg', {
                    width: 14, height: 14, viewBox: '0 0 24 24', fill: 'currentColor',
                    className: 'text-teal-500/60 group-hover:text-teal-400 transition-colors'
                  },
                    React.createElement('path', { d: PUB_TYPE_ICONS[pub.type] || PUB_TYPE_ICONS.other })
                  )
                ),
                React.createElement('div', { className: 'flex-1 min-w-0' },
                  React.createElement('div', { className: 'text-[12px] text-gray-200 group-hover:text-teal-400 transition-colors line-clamp-2 leading-snug' }, pub.title),
                  React.createElement('div', { className: 'flex items-center gap-2 mt-1' },
                    React.createElement('span', { className: 'text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-gray-500 capitalize' },
                      PUB_TYPE_LABELS[pub.type] || 'Publication'
                    ),
                    pub.source && React.createElement('span', { className: 'text-[10px] text-gray-600' }, pub.source)
                  ),
                  pub.snippet && React.createElement('p', { className: 'text-[10px] text-gray-500 mt-1 line-clamp-2 leading-relaxed' }, pub.snippet)
                ),
                React.createElement('svg', {
                  width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2,
                  className: 'text-gray-600 group-hover:text-teal-400 transition-colors shrink-0 mt-1'
                },
                  React.createElement('path', { d: 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6' }),
                  React.createElement('polyline', { points: '15 3 21 3 21 9' }),
                  React.createElement('line', { x1: 10, y1: 14, x2: 21, y2: 3 })
                )
              )
            )
          ),
          publications && publications.length === 0 && !loadingPubs &&
            React.createElement('p', { className: 'text-[11px] text-gray-600 italic py-1' }, 'No published content found for this expert.')
        ),
        React.createElement('div', null,
          React.createElement('div', { className: 'flex items-center gap-2 mb-2' },
            React.createElement('h4', { className: 'text-[10px] text-gray-500 uppercase tracking-wider' }, 'Expertise'),
            React.createElement('span', { className: 'text-[9px] text-gray-600 italic' }, 'click to find experts')
          ),
          React.createElement('div', { className: 'flex gap-1.5 flex-wrap' },
            (expert.expertise || []).map((ex, j) =>
              React.createElement('button', {
                key: j,
                onClick: () => searchExpertsByTopic(ex),
                className: cn(
                  'text-[11px] px-2 py-0.5 rounded-md border transition-all duration-150 cursor-pointer',
                  topicExperts?.topic === ex
                    ? 'bg-teal-500/15 text-teal-300 border-teal-500/30'
                    : 'bg-white/5 text-gray-300 border-white/5 hover:bg-teal-500/10 hover:text-teal-300 hover:border-teal-500/20'
                )
              }, ex)
            )
          ),
          // Topic experts results inline
          topicExperts && React.createElement('div', { className: 'mt-3' },
            topicExperts.loading && React.createElement('div', { className: 'flex items-center gap-2 py-3' },
              React.createElement('div', { className: 'w-3 h-3 border border-teal-400/50 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
              React.createElement('span', { className: 'text-xs text-gray-500' }, `Finding experts in ${topicExperts.topic}...`)
            ),
            topicExperts.error && React.createElement('p', { className: 'text-xs text-red-400 py-2' }, topicExperts.error),
            !topicExperts.loading && topicExperts.experts.length > 0 && React.createElement('div', {
              className: 'bg-white/[0.02] border border-white/5 rounded-lg overflow-hidden'
            },
              React.createElement('div', { className: 'px-3 py-2 border-b border-white/5 flex items-center justify-between' },
                React.createElement('span', { className: 'text-[10px] text-teal-400 uppercase tracking-wider font-medium' },
                  `${topicExperts.topic} Experts`
                ),
                React.createElement('span', { className: 'text-[10px] text-gray-600' }, `${topicExperts.experts.length} found`)
              ),
              React.createElement('div', { className: 'divide-y divide-white/5' },
                topicExperts.experts.map((te) =>
                  React.createElement('button', {
                    key: te.id,
                    onClick: () => openExpert(te),
                    className: 'w-full text-left px-3 py-2.5 hover:bg-white/[0.03] transition-colors group'
                  },
                    React.createElement('div', { className: 'flex items-start justify-between gap-2' },
                      React.createElement('div', { className: 'min-w-0 flex-1' },
                        React.createElement('div', { className: 'text-sm text-white group-hover:text-teal-400 transition-colors truncate' }, te.name),
                        React.createElement('div', { className: 'text-[11px] text-gray-500 truncate mt-0.5' }, formatCurrentRole(te))
                      ),
                      React.createElement(ScoreBadge, { score: te.score, small: true })
                    ),
                    React.createElement('p', { className: 'text-[10px] text-gray-600 mt-1 line-clamp-2' }, te.connectionToCompany),
                    React.createElement('div', { className: 'flex items-center gap-2 mt-1.5', onClick: (ev) => ev.stopPropagation() },
                      React.createElement(EmailExpertButton, { expert: te, companyName }),
                      React.createElement(LinkedInButton, { url: te.linkedinUrl, name: te.name, expert: te })
                    )
                  )
                )
              )
            ),
            !topicExperts.loading && topicExperts.experts.length === 0 && !topicExperts.error &&
              React.createElement('p', { className: 'text-xs text-gray-600 py-2' }, 'No experts found for this topic.')
          )
        ),
        React.createElement('div', null,
          React.createElement('h4', { className: 'text-[10px] text-gray-500 uppercase tracking-wider mb-2' }, 'Score Breakdown'),
          React.createElement('div', { className: 'grid grid-cols-4 gap-2' },
            [
              { label: 'Proximity', val: expert.score?.proximity, weight: '25%' },
              { label: 'Recency', val: expert.score?.recency, weight: '20%' },
              { label: 'Relevance', val: expert.score?.relevance, weight: '30%' },
              { label: 'Uniqueness', val: expert.score?.uniqueness, weight: '25%' }
            ].map(s =>
              React.createElement('div', { key: s.label, className: 'bg-white/[0.03] rounded-lg p-2.5 border border-white/5 text-center' },
                React.createElement('div', { className: 'text-lg font-semibold text-white tabular-nums' }, s.val),
                React.createElement('div', { className: 'text-[9px] text-gray-500 mt-0.5' }, s.label),
                React.createElement('div', { className: 'text-[8px] text-gray-600' }, s.weight)
              )
            )
          )
        ),
        React.createElement('div', { className: 'border-t border-white/5' }),
        React.createElement('div', null,
          React.createElement('div', { className: 'flex items-center justify-between mb-2' },
            React.createElement('h4', { className: 'text-[10px] text-gray-500 uppercase tracking-wider' }, 'Tailored Research Questions'),
            !questions && React.createElement('button', {
              onClick: loadQuestions, disabled: loadingQ,
              className: 'text-[10px] text-teal-400 hover:text-teal-300 transition-colors'
            }, loadingQ ? 'Generating...' : 'Generate')
          ),
          loadingQ && React.createElement('div', { className: 'flex items-center gap-2 py-3' },
            React.createElement('div', { className: 'w-3 h-3 border border-teal-400/50 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
            React.createElement('span', { className: 'text-xs text-gray-500' }, 'Generating questions tailored to this expert...')
          ),
          questions && React.createElement('ol', { className: 'space-y-2' },
            questions.map((q, i) =>
              React.createElement('li', { key: i, className: 'flex gap-2 text-[12px] text-gray-300' },
                React.createElement('span', { className: 'text-gray-600 font-mono tabular-nums shrink-0' }, `${i + 1}.`),
                React.createElement('span', null, q)
              )
            )
          )
        ),
        expert.sourceNote && React.createElement('div', { className: 'text-[10px] text-gray-600 italic pt-2 border-t border-white/5' },
          'Source: ', expert.sourceNote
        ),
        React.createElement(Disclaimer)
      )
    )
  );
}

// ============================================================
// CLICKABLE EXPERT NAME
// ============================================================
function ExpertName({ expert, className }) {
  const { openExpert } = React.useContext(ExpertPanelContext);
  return React.createElement('button', {
    onClick: (e) => { e.stopPropagation(); openExpert(expert); },
    className: cn('text-left hover:text-teal-400 transition-colors cursor-pointer', className || 'text-white')
  }, expert.name);
}


// ============================================================
// SCREEN 2: RELATIONSHIP MAP (D3 Force-Directed Graph)
// ============================================================
const RELATION_COLORS = {
  competitor: '#ff6b6b',
  supplier: '#748ffc',
  customer: '#ffd43b',
  center: '#20c997',
  expanded: '#20c997',
};

function RelationshipMap({ initialCompany }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const simRef = useRef(null);
  const [nodes, setNodes] = useState([]);
  const [links, setLinks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingNode, setLoadingNode] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [expertPanel, setExpertPanel] = useState(null);
  const [ticker, setTicker] = useState(null);
  const expandedRef = useRef(new Set());
  const graphDataRef = useRef({ nodes: [], links: [] });

  // Initialize from the company loaded in Company Research tab
  useEffect(() => {
    if (initialCompany && nodes.length === 0) {
      buildInitialGraph(initialCompany);
    }
  }, [initialCompany]);

  function buildInitialGraph(company) {
    const centerNode = {
      id: company.name,
      label: company.name,
      type: 'center',
      ticker: company.ticker,
      radius: 28,
      fx: null, fy: null,
      isCenter: true,
    };

    const newNodes = [centerNode];
    const newLinks = [];

    const addEntities = (items, relType) => {
      (items || []).forEach(name => {
        const nodeId = `${name}`;
        if (!newNodes.find(n => n.id === nodeId)) {
          newNodes.push({
            id: nodeId,
            label: name,
            type: relType,
            radius: 18,
            parentId: company.name,
          });
        }
        newLinks.push({
          source: company.name,
          target: nodeId,
          type: relType,
        });
      });
    };

    addEntities(company.competitors, 'competitor');
    addEntities(company.suppliers, 'supplier');
    addEntities(company.customers, 'customer');

    expandedRef.current = new Set([company.name]);
    graphDataRef.current = { nodes: newNodes, links: newLinks };
    setNodes([...newNodes]);
    setLinks([...newLinks]);
    setTicker(company.ticker);
  }

  // Handle expand-node (click to load a node's ecosystem)
  const expandNode = useCallback(async (node) => {
    if (expandedRef.current.has(node.id)) return;
    if (node.isCenter) return; // Already expanded

    setLoadingNode(node.id);
    try {
      const data = await apiFetch('/api/expand-node', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ companyName: node.label })
      });

      expandedRef.current.add(node.id);

      const curNodes = [...graphDataRef.current.nodes];
      const curLinks = [...graphDataRef.current.links];

      // Mark this node as expanded
      const idx = curNodes.findIndex(n => n.id === node.id);
      if (idx >= 0) {
        curNodes[idx] = { ...curNodes[idx], expanded: true, radius: 22 };
      }

      const addEntities = (items, relType) => {
        (items || []).forEach(name => {
          const nodeId = `${name}`;
          if (!curNodes.find(n => n.id === nodeId)) {
            curNodes.push({
              id: nodeId,
              label: name,
              type: relType,
              radius: 14,
              parentId: node.id,
            });
          }
          const linkId = `${node.id}->${nodeId}`;
          if (!curLinks.find(l => (l.source?.id || l.source) === node.id && (l.target?.id || l.target) === nodeId)) {
            curLinks.push({
              source: node.id,
              target: nodeId,
              type: relType,
              id: linkId,
            });
          }
        });
      };

      addEntities(data.competitors, 'competitor');
      addEntities(data.suppliers, 'supplier');
      addEntities(data.customers, 'customer');

      graphDataRef.current = { nodes: curNodes, links: curLinks };
      setNodes([...curNodes]);
      setLinks([...curLinks]);
    } catch (err) {
      console.error('Expand node failed:', err);
    }
    setLoadingNode(null);
  }, []);

  // D3 Force Simulation
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    const container = containerRef.current;
    const width = container.clientWidth;
    const height = container.clientHeight;

    svg.attr('width', width).attr('height', height);

    // Clear previous
    svg.selectAll('*').remove();

    const g = svg.append('g');

    // Zoom
    const zoom = d3.zoom()
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => g.attr('transform', event.transform));
    svg.call(zoom);

    // Initial center transform
    svg.call(zoom.transform, d3.zoomIdentity.translate(width / 2, height / 2).scale(0.85));

    // Create simulation
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(d => {
        const srcExpanded = expandedRef.current.has(d.source?.id || d.source);
        const tgtExpanded = expandedRef.current.has(d.target?.id || d.target);
        if (srcExpanded || tgtExpanded) return 120;
        return 80;
      }).strength(0.4))
      .force('charge', d3.forceManyBody().strength(d => d.isCenter ? -500 : d.expanded ? -300 : -150))
      .force('center', d3.forceCenter(0, 0).strength(0.05))
      .force('collision', d3.forceCollide().radius(d => d.radius + 8))
      .alphaDecay(0.02);

    simRef.current = sim;

    // Links
    const linkSel = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('class', 'link-line')
      .attr('stroke', d => RELATION_COLORS[d.type] || '#555')
      .attr('stroke-width', 1.5);

    // Node groups
    const nodeSel = g.append('g')
      .selectAll('g')
      .data(nodes, d => d.id)
      .join('g')
      .attr('cursor', 'pointer')
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', (event, d) => {
          d.fx = event.x; d.fy = event.y;
        })
        .on('end', (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    // Node circles
    nodeSel.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => {
        if (d.isCenter) return RELATION_COLORS.center;
        if (d.expanded) return RELATION_COLORS.expanded + '40';
        return (RELATION_COLORS[d.type] || '#555') + '30';
      })
      .attr('stroke', d => {
        if (d.isCenter) return RELATION_COLORS.center;
        if (d.expanded) return RELATION_COLORS.expanded;
        return RELATION_COLORS[d.type] || '#555';
      })
      .attr('stroke-width', d => d.isCenter ? 3 : d.expanded ? 2 : 1.5)
      .attr('class', 'node-circle');

    // Node labels
    nodeSel.append('text')
      .text(d => d.label.length > 16 ? d.label.slice(0, 14) + '...' : d.label)
      .attr('text-anchor', 'middle')
      .attr('dy', d => d.radius + 14)
      .attr('fill', d => d.isCenter ? '#20c997' : '#9ca3af')
      .attr('font-size', d => d.isCenter ? '11px' : d.expanded ? '10px' : '9px')
      .attr('font-weight', d => d.isCenter ? '600' : '400')
      .attr('font-family', 'Inter, sans-serif');

    // Relationship type indicator
    nodeSel.filter(d => !d.isCenter && !d.expanded)
      .append('text')
      .text(d => d.type === 'competitor' ? 'C' : d.type === 'supplier' ? 'S' : 'Cu')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', d => RELATION_COLORS[d.type] || '#888')
      .attr('font-size', '8px')
      .attr('font-weight', '600')
      .attr('font-family', 'Inter, sans-serif');

    // Center node text
    nodeSel.filter(d => d.isCenter)
      .append('text')
      .text(d => d.ticker || d.label.slice(0, 4))
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', '#fff')
      .attr('font-size', '11px')
      .attr('font-weight', '700')
      .attr('font-family', 'JetBrains Mono, monospace');

    // Expanded node text
    nodeSel.filter(d => d.expanded)
      .append('text')
      .text('\u2714')
      .attr('text-anchor', 'middle')
      .attr('dy', '0.35em')
      .attr('fill', RELATION_COLORS.expanded)
      .attr('font-size', '10px');

    // Click handler — single click expands network, shows panel only if already expanded
    nodeSel.on('click', (event, d) => {
      event.stopPropagation();
      if (d.isCenter) {
        setSelectedNode(d);
      } else if (!expandedRef.current.has(d.id)) {
        // Auto-expand on first click
        expandNode(d);
      } else {
        // Already expanded — show action panel
        setSelectedNode(d);
      }
    });

    // Tick
    sim.on('tick', () => {
      linkSel
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
    });

    return () => sim.stop();
  }, [nodes, links]);

  // Empty state — no company loaded yet
  if (!initialCompany) {
    return React.createElement('div', { className: 'flex flex-col items-center justify-center h-full px-8' },
      React.createElement('div', { className: 'text-center max-w-md' },
        React.createElement('svg', { width: 64, height: 64, viewBox: '0 0 64 64', fill: 'none', className: 'mx-auto mb-6 opacity-30' },
          React.createElement('circle', { cx: 32, cy: 32, r: 8, fill: '#20c997' }),
          React.createElement('circle', { cx: 12, cy: 16, r: 5, stroke: '#20c997', strokeWidth: 1.5, fill: 'none' }),
          React.createElement('circle', { cx: 52, cy: 16, r: 5, stroke: '#748ffc', strokeWidth: 1.5, fill: 'none' }),
          React.createElement('circle', { cx: 12, cy: 48, r: 5, stroke: '#ffd43b', strokeWidth: 1.5, fill: 'none' }),
          React.createElement('circle', { cx: 52, cy: 48, r: 5, stroke: '#ff6b6b', strokeWidth: 1.5, fill: 'none' }),
          React.createElement('line', { x1: 26, y1: 27, x2: 16, y2: 19, stroke: '#20c997', strokeWidth: 1, opacity: 0.5 }),
          React.createElement('line', { x1: 38, y1: 27, x2: 48, y2: 19, stroke: '#748ffc', strokeWidth: 1, opacity: 0.5 }),
          React.createElement('line', { x1: 26, y1: 37, x2: 16, y2: 45, stroke: '#ffd43b', strokeWidth: 1, opacity: 0.5 }),
          React.createElement('line', { x1: 38, y1: 37, x2: 48, y2: 45, stroke: '#ff6b6b', strokeWidth: 1, opacity: 0.5 })
        ),
        React.createElement('h3', { className: 'text-lg font-medium text-gray-300 mb-2' }, 'Relationship Map'),
        React.createElement('p', { className: 'text-sm text-gray-500 leading-relaxed' },
          'Search a company in the Company Research tab first. The relationship map will automatically populate with its ecosystem — competitors, suppliers, and customers. Click any node to expand its connections or generate experts.'
        )
      )
    );
  }

  return React.createElement('div', { className: 'h-full flex flex-col animate-fade-in' },
    // Toolbar
    React.createElement('div', { className: 'flex items-center justify-between px-4 py-3 border-b border-white/5 bg-navy-900/50 shrink-0' },
      React.createElement('div', { className: 'flex items-center gap-4' },
        React.createElement('h2', { className: 'text-sm font-medium text-white' }, `${initialCompany.name} Ecosystem`),
        React.createElement('div', { className: 'flex items-center gap-3' },
          React.createElement('div', { className: 'flex items-center gap-1.5' },
            React.createElement('div', { className: 'w-2.5 h-2.5 rounded-full bg-red-400/60 border border-red-400' }),
            React.createElement('span', { className: 'text-[10px] text-gray-500' }, 'Competitors')
          ),
          React.createElement('div', { className: 'flex items-center gap-1.5' },
            React.createElement('div', { className: 'w-2.5 h-2.5 rounded-full bg-indigo-400/60 border border-indigo-400' }),
            React.createElement('span', { className: 'text-[10px] text-gray-500' }, 'Suppliers')
          ),
          React.createElement('div', { className: 'flex items-center gap-1.5' },
            React.createElement('div', { className: 'w-2.5 h-2.5 rounded-full bg-yellow-400/60 border border-yellow-400' }),
            React.createElement('span', { className: 'text-[10px] text-gray-500' }, 'Customers')
          )
        )
      ),
      loadingNode && React.createElement('div', { className: 'flex items-center gap-2 text-xs text-gray-400' },
        React.createElement('div', { className: 'w-3 h-3 border border-teal-400/50 border-t-teal-400 rounded-full', style: { animation: 'spin 1s linear infinite' } }),
        `Expanding ${loadingNode}...`
      )
    ),

    // Graph canvas
    React.createElement('div', { ref: containerRef, className: 'flex-1 relative overflow-hidden' },
      React.createElement('svg', { ref: svgRef, className: 'w-full h-full' }),

      // Selected node action panel
      selectedNode && !selectedNode.isCenter && React.createElement('div', {
        className: 'absolute bottom-4 left-1/2 -translate-x-1/2 bg-navy-950 border border-white/10 rounded-xl px-5 py-4 shadow-2xl min-w-[320px] max-w-[400px]',
        style: { animation: 'fadeIn 0.2s ease-out' }
      },
        React.createElement('div', { className: 'flex items-start justify-between mb-3' },
          React.createElement('div', null,
            React.createElement('h3', { className: 'text-sm font-medium text-white' }, selectedNode.label),
            React.createElement('p', { className: 'text-[10px] text-gray-500 capitalize mt-0.5' },
              selectedNode.type === 'competitor' ? 'Competitor' :
              selectedNode.type === 'supplier' ? 'Supplier' :
              selectedNode.type === 'customer' ? 'Customer' : selectedNode.type
            )
          ),
          React.createElement('button', {
            onClick: () => setSelectedNode(null),
            className: 'text-gray-500 hover:text-gray-300 p-1'
          },
            React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
              React.createElement('path', { d: 'M6 18L18 6M6 6l12 12' })
            )
          )
        ),
        expandedRef.current.has(selectedNode.id) && React.createElement('p', { className: 'text-[10px] text-teal-400/60 mb-2 flex items-center gap-1.5' },
          React.createElement('svg', { width: 12, height: 12, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
            React.createElement('path', { d: 'M20 6L9 17l-5-5' })
          ),
          'Network expanded'
        ),
        React.createElement('div', { className: 'flex items-center gap-2' },
          React.createElement('button', {
            onClick: () => { setExpertPanel({ entityName: selectedNode.label, entityType: selectedNode.type }); setSelectedNode(null); },
            className: 'flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-xs font-medium bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 hover:bg-indigo-500/20 transition-colors'
          },
            React.createElement('svg', { width: 14, height: 14, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2 },
              React.createElement('path', { d: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z' })
            ),
            'Find Experts'
          )
        )
      ),

      // Instructions hint
      nodes.length > 0 && !selectedNode && React.createElement('div', {
        className: 'absolute bottom-4 left-1/2 -translate-x-1/2 text-[10px] text-gray-600 bg-navy-950/80 px-3 py-1.5 rounded-full border border-white/5'
      }, 'Click a node to expand its network \u00b7 Click again for experts \u00b7 Drag to rearrange \u00b7 Scroll to zoom')
    ),

    // Entity experts panel overlay
    expertPanel && React.createElement(EntityExpertsPanel, {
      entityName: expertPanel.entityName,
      entityType: expertPanel.entityType,
      parentTicker: ticker || '',
      parentCompany: initialCompany?.name || '',
      onClose: () => setExpertPanel(null)
    })
  );
}


// ============================================================
// SCREEN 3: USER GUIDE
// ============================================================
function UserGuide() {
  const Section = ({ title, children }) => React.createElement('div', { className: 'bg-white/[0.03] rounded-xl border border-white/5 p-5' },
    React.createElement('h3', { className: 'text-sm font-semibold text-white mb-3' }, title),
    children
  );
  const P = ({ children }) => React.createElement('p', { className: 'text-[13px] text-gray-300 leading-relaxed mb-2' }, children);
  const Li = ({ children }) => React.createElement('li', { className: 'flex gap-2 text-[13px] text-gray-300 leading-relaxed' },
    React.createElement('span', { className: 'text-teal-400/60 shrink-0' }, '\u2022'), React.createElement('span', null, children)
  );
  const SubHead = ({ children }) => React.createElement('h4', { className: 'text-xs font-medium text-gray-400 uppercase tracking-wider mt-4 mb-2' }, children);

  return React.createElement('div', { className: 'space-y-5 max-w-3xl mx-auto animate-fade-in' },
    React.createElement('div', { className: 'mb-2' },
      React.createElement('h2', { className: 'text-lg font-semibold text-white' }, 'User Guide'),
      React.createElement('p', { className: 'text-sm text-gray-500 mt-1' }, 'How to use M.D. Sass Expert Discovery')
    ),

    // Getting Started
    React.createElement(Section, { title: 'Getting Started' },
      React.createElement(P, null, 'Expert Discovery helps equity research analysts discover and evaluate potential expert network consultants for any publicly traded company (S&P 500 and Russell 3000 tickers are pre-loaded for fast search). Enter a ticker symbol or company name to begin.'),
      React.createElement('ol', { className: 'space-y-1.5 list-decimal list-inside text-[13px] text-gray-300' },
        React.createElement('li', null, 'Type a ticker (e.g., AAPL, NVDA, PWR) or company name in the search bar.'),
        React.createElement('li', null, 'The company profile, executive team, and ecosystem grid load first. Experts generate in the background and appear automatically when ready.'),
        React.createElement('li', null, 'Browse the expert network table at the bottom for scored expert recommendations.'),
        React.createElement('li', null, 'Click any expert name to view their profile, score breakdown, and tailored research questions.'),
        React.createElement('li', null, 'Switch freely between tabs — your Company Research query is preserved when you visit Relationship Map or User Guide and return.')
      )
    ),

    // Company Research
    React.createElement(Section, { title: 'Company Research' },
      React.createElement(SubHead, null, 'Ecosystem Analysis'),
      React.createElement(P, null, 'After searching a company, you see its business model summary, executive team, and ecosystem grid. Each category (End Markets, Competitors, Suppliers, Customers, Distributors, Regulators) lists relevant companies or entities.'),
      React.createElement(SubHead, null, 'Managing Ecosystem Companies'),
      React.createElement(P, null, 'Each ecosystem section supports full add, edit, and delete controls:'),
      React.createElement('ul', { className: 'space-y-1' },
        React.createElement(Li, null, 'Add — Click the "+ Add" button at the bottom of any section to manually add a company the system may have missed.'),
        React.createElement(Li, null, 'Edit — Hover over any company name and click the pencil icon. An inline editor appears where you can rename it, then press Enter or click the checkmark to save.'),
        React.createElement(Li, null, 'Delete — Hover over any company name and click the X icon to remove it from the list.')
      ),
      React.createElement(P, null, 'All additions, edits, and deletions persist while researching a company. Switching tabs and returning preserves your changes.'),
      React.createElement(SubHead, null, 'Executive Team'),
      React.createElement(P, null, 'Click the Executive Team section to expand it. Click any executive to find former direct reports who have left the company and could serve as expert consultants.'),
      React.createElement(SubHead, null, 'Ecosystem Entities'),
      React.createElement(P, null, 'Every listed company in the ecosystem grid is clickable. Clicking one opens a panel showing experts from that entity who could provide insights relevant to your target company.'),
      React.createElement(SubHead, null, 'Expert Network Table'),
      React.createElement(P, null, 'The main expert table shows experts sorted by overall score. Each row shows their current role, former role, type, expertise areas, years of experience, connection to the company, and composite score. Use "Find More Experts" to generate additional candidates.'),
      React.createElement(SubHead, null, 'Background Pre-loading'),
      React.createElement(P, null, 'After the initial results load, the system pre-loads experts for executives and ecosystem entities in the background. A progress bar shows the status. Once complete, clicking on any executive or entity returns results instantly.')
    ),

    // Expert Profiles
    React.createElement(Section, { title: 'Expert Profiles & Actions' },
      React.createElement(P, null, 'Click any expert name to open their profile panel. The panel includes:'),
      React.createElement('ul', { className: 'space-y-1' },
        React.createElement(Li, null, 'Relevant Experience — Current role and company, former role, and years of experience.'),
        React.createElement(Li, null, 'Connection to Company — How they relate to the target company.'),
        React.createElement(Li, null, 'Expertise Tags — Click any tag to discover more experts in that topic area.'),
        React.createElement(Li, null, 'Score Breakdown — Detailed scoring across all four dimensions.'),
        React.createElement(Li, null, 'Research Questions — Dynamically generated questions tailored to each expert\'s unique experience.')
      ),
      React.createElement(SubHead, null, 'LinkedIn'),
      React.createElement(P, null, 'Every expert has a LinkedIn button that opens a LinkedIn people search for their name. Use this to verify their identity and current role before outreach.'),
      React.createElement(SubHead, null, 'Request via Expert Network'),
      React.createElement(P, null, 'The "Request" button generates a pre-formatted email to your expert network consultant requesting they source that specific expert. The email includes the expert\'s name, role, and connection to the company under research.')
    ),

    // Score Breakdown
    React.createElement(Section, { title: 'Score Breakdown' },
      React.createElement(P, null, 'Each expert receives a composite score (1-5 scale) based on four weighted dimensions:'),
      React.createElement('div', { className: 'grid grid-cols-2 gap-3 mt-3' },
        [{
          label: 'Relevance', weight: '30%', color: 'text-teal-400',
          desc: 'How directly their experience relates to the target company. Considers industry overlap, role relevance, and domain expertise.'
        }, {
          label: 'Proximity', weight: '25%', color: 'text-blue-400',
          desc: 'How close they were to the target company. Direct employees score highest, followed by suppliers, customers, and competitors.'
        }, {
          label: 'Uniqueness', weight: '25%', color: 'text-purple-400',
          desc: 'How differentiated their perspective is. Experts with rare, hard-to-replicate insights score higher than those with widely available knowledge.'
        }, {
          label: 'Recency', weight: '20%', color: 'text-amber-400',
          desc: 'How recent their relevant experience is. More recent experience is weighted higher since industry dynamics change quickly.'
        }].map(s =>
          React.createElement('div', { key: s.label, className: 'bg-white/[0.02] rounded-lg p-3 border border-white/5' },
            React.createElement('div', { className: 'flex items-center justify-between mb-1' },
              React.createElement('span', { className: `text-xs font-medium ${s.color}` }, s.label),
              React.createElement('span', { className: 'text-[10px] text-gray-500 font-mono' }, s.weight)
            ),
            React.createElement('p', { className: 'text-[11px] text-gray-400 leading-relaxed' }, s.desc)
          )
        )
      ),
      React.createElement('div', { className: 'mt-3 text-[12px] text-gray-500' },
        'Overall Score = (Relevance \u00d7 0.30) + (Proximity \u00d7 0.25) + (Uniqueness \u00d7 0.25) + (Recency \u00d7 0.20). ',
        'Scores \u2265 4.0 are labeled "High", \u2265 3.0 "Medium", below 3.0 "Low".'
      )
    ),

    // How Experts Are Sourced
    React.createElement(Section, { title: 'How Experts Are Sourced' },
      React.createElement(P, null, 'Expert candidates are generated through a multi-step pipeline:'),
      React.createElement('ol', { className: 'space-y-2 list-decimal list-inside text-[13px] text-gray-300' },
        React.createElement('li', null, 'Web Search — The system queries for real professionals associated with the target company and its ecosystem using multiple search engines.'),
        React.createElement('li', null, 'AI Generation — Using web search context, an AI model generates structured expert profiles with verifiable names, titles, and affiliations.'),
        React.createElement('li', null, 'Cross-Model Verification — A separate AI model independently verifies each expert, checking name accuracy, current role, and company affiliation.'),
        React.createElement('li', null, 'Reconciliation — Any conflicts between the generating and verifying models are reconciled to maximize accuracy.')
      ),
      React.createElement('div', { className: 'bg-amber-500/5 border border-amber-500/10 rounded-lg p-3 mt-3' },
        React.createElement('p', { className: 'text-[11px] text-amber-200/60 leading-relaxed' },
          'Note: While the system strives for accuracy, AI-generated expert profiles should be independently verified before outreach. LinkedIn links are provided to facilitate verification.'
        )
      )
    ),

    // Relationship Map
    React.createElement(Section, { title: 'Relationship Map' },
      React.createElement(P, null, 'The Relationship Map provides a visual, interactive graph of the company ecosystem. After researching a company, switch to the Relationship Map tab to see it visualized.'),
      React.createElement('ul', { className: 'space-y-1' },
        React.createElement(Li, null, 'Click any node to expand its own suppliers, competitors, and customers.'),
        React.createElement(Li, null, 'Click "Find Experts" on a node to generate expert candidates from that entity.'),
        React.createElement(Li, null, 'Drag nodes to rearrange the layout. Scroll to zoom in/out.'),
        React.createElement(Li, null, 'Color coding: Red = Competitors, Blue = Suppliers, Yellow = Customers, Green = Center/Expanded.')
      )
    ),

    // Requesting an Expert
    React.createElement(Section, { title: 'Requesting an Expert' },
      React.createElement(P, null, 'The "Request" button on each expert generates a pre-formatted email to your expert network consultant. The email includes:'),
      React.createElement('ul', { className: 'space-y-1' },
        React.createElement(Li, null, 'The expert\'s name, current role, and former role.'),
        React.createElement(Li, null, 'Their connection to the company under research.'),
        React.createElement(Li, null, 'A request to schedule a consultation call.')
      ),
      React.createElement(P, { children: 'This opens your default email client with the message pre-populated. Edit the recipient and customize the message as needed.' })
    ),

    // How Expertise Tags Work
    React.createElement(Section, { title: 'How Expertise Is Defined' },
      React.createElement(P, null, 'Each expert is tagged with 2-4 areas of expertise based on their career history, current role, and connection to the target company. These tags represent their primary knowledge domains.'),
      React.createElement(P, { children: 'On the bio panel, clicking any expertise tag triggers a search for additional experts with deep knowledge in that specific topic. This is useful for following a research thread across multiple experts.' })
    ),

    React.createElement(Disclaimer)
  );
}

// ============================================================
// MAIN APP
// ============================================================
function App() {
  const [activeTab, setActiveTab] = useState('research');
  const [collapsed, setCollapsed] = useState(false);
  const [selectedExpert, setSelectedExpert] = useState(null);
  const [loadedCompany, setLoadedCompany] = useState(null);
  const [researchTicker, setResearchTicker] = useState(null);

  const openExpert = useCallback((expert) => setSelectedExpert(expert), []);
  const closeExpert = useCallback(() => setSelectedExpert(null), []);
  const onCompanyLoaded = useCallback((company) => setLoadedCompany(company), []);

  const renderScreen = () => {
    if (activeTab === 'map') {
      return React.createElement(RelationshipMap, { initialCompany: loadedCompany });
    }
    if (activeTab === 'guide') {
      return React.createElement(UserGuide);
    }
    return React.createElement(CompanyResearch, { onCompanyLoaded, ticker: researchTicker, setTicker: setResearchTicker });
  };

  return React.createElement(ExpertPanelContext.Provider, { value: { openExpert } },
    React.createElement('div', { className: 'h-screen flex bg-navy-900' },
      React.createElement(Sidebar, { activeTab, setActiveTab, collapsed, setCollapsed }),
      React.createElement('div', { className: 'flex-1 flex flex-col min-w-0' },
        // Top Bar with M.D. Sass branding
        React.createElement('header', { className: 'h-12 border-b border-white/5 flex items-center justify-between px-5 bg-navy-900/80 backdrop-blur shrink-0' },
          React.createElement('div', { className: 'flex items-center gap-3' },
            React.createElement('span', { className: 'text-xs font-semibold tracking-wide text-gray-300' }, 'M.D. SASS'),
            React.createElement('span', { className: 'text-gray-700' }, '\u2014'),
            React.createElement('span', { className: 'text-xs text-gray-500' }, 'Expert Discovery'),
            React.createElement('span', { className: 'text-gray-700' }, '/'),
            React.createElement('span', { className: 'text-xs text-gray-300 font-medium' },
              activeTab === 'map' ? 'Relationship Map' : activeTab === 'guide' ? 'User Guide' : 'Research'
            )
          ),
          React.createElement('div', { className: 'text-[10px] text-gray-600' }, 'v10.5')
        ),
        // Main Content
        React.createElement('main', {
          className: cn(
            'flex-1 overflow-y-auto overscroll-contain scrollbar-thin',
            activeTab === 'map' ? '' : 'p-5'
          )
        }, renderScreen())
      ),
      selectedExpert && React.createElement(ExpertDetailPanel, { expert: selectedExpert, onClose: closeExpert })
    )
  );
}

// ============================================================
// MOUNT
// ============================================================
const root = createRoot(document.getElementById('root'));
root.render(React.createElement(App));
