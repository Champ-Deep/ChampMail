import React, { useState } from 'react';
import { ArrowRight, Globe, Database, Cpu, Users, BarChart, Layers, ShieldCheck, Briefcase } from 'lucide-react';

const RoadmapVisualization = () => {
  const [activeView, setActiveView] = useState('strategic'); // 'strategic' or 'sitemap'

  return (
    <div className="w-full max-w-7xl mx-auto p-8 min-h-screen">
      
      {/* Header */}
      <div className="mb-12 text-center relative z-10">
        <h1 className="text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-slate-900 to-slate-700 mb-4 tracking-tight">
          Lake B2B Navigation Restructure <span className="text-blue-600">2026</span>
        </h1>
        <p className="text-slate-500 text-lg max-w-2xl mx-auto font-medium leading-relaxed">
          The strategic evolution from a transactional "Data Vendor" to a comprehensive 
          <span className="text-slate-900 font-semibold"> "Growth Platform Ecosystem."</span>
        </p>
        
        {/* Toggle Controls */}
        <div className="inline-flex justify-center mt-8 p-1.5 bg-slate-200/50 backdrop-blur-md rounded-full border border-slate-200 shadow-inner">
          <button 
            onClick={() => setActiveView('strategic')}
            className={`px-6 py-2.5 rounded-full text-sm font-semibold transition-all duration-300 ease-out focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
              activeView === 'strategic' 
                ? 'bg-white text-blue-700 shadow-md transform scale-105' 
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
            }`}
          >
            Strategic Roadmap
          </button>
          <button 
            onClick={() => setActiveView('sitemap')}
            className={`px-6 py-2.5 rounded-full text-sm font-semibold transition-all duration-300 ease-out focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
              activeView === 'sitemap' 
                ? 'bg-white text-blue-700 shadow-md transform scale-105' 
                : 'text-slate-500 hover:text-slate-700 hover:bg-slate-200/50'
            }`}
          >
            Detailed Sitemap Comparison
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="grid grid-cols-1 md:grid-cols-12 gap-8 relative">
        
        {/* LEFT COLUMN: CURRENT STATE */}
        <div className="md:col-span-4 relative group">
            <div className="absolute inset-0 bg-white/40 backdrop-blur-xl rounded-2xl shadow-glass border border-white/50 transition-all duration-500 group-hover:shadow-lg"></div>
            <div className="relative p-8">
                <div className="flex items-center space-x-3 mb-6 border-b border-slate-200/60 pb-5">
                    <div className="bg-slate-100 p-2.5 rounded-xl shadow-sm">
                    <Database className="w-5 h-5 text-slate-500" />
                    </div>
                    <div>
                    <h2 className="font-bold text-slate-600 text-lg">Current State (2025)</h2>
                    <span className="inline-block mt-1 text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-500 px-2 py-0.5 rounded-md border border-slate-200">
                        The "Commodity" Model
                    </span>
                    </div>
                </div>

                <div className="space-y-4">
                    <NavItem 
                    title="Data & Lists" 
                    subtext="Selling raw asset rows."
                    icon={<Database size={16} />}
                    theme="muted"
                    />
                    <NavItem 
                    title="Marketing Services" 
                    subtext="Tactical execution."
                    icon={<Users size={16} />}
                    theme="muted"
                    />
                    <NavItem 
                    title="Resources" 
                    subtext="Blogs, standard content."
                    icon={<Layers size={16} />}
                    theme="muted"
                    />
                    <NavItem 
                    title="Company / Contact" 
                    subtext="Standard corporate pages."
                    icon={<Globe size={16} />}
                    theme="muted"
                    />
                    
                    <div className="mt-8 p-5 bg-red-50/80 rounded-xl border border-red-100 text-xs text-red-900 leading-relaxed shadow-sm backdrop-blur-sm">
                    <strong className="block mb-1 text-red-800 uppercase tracking-wide">Pain Point</strong> 
                    Client perceives us as just another list vendor. Low extensive value.
                    </div>
                </div>
            </div>
        </div>

        {/* MIDDLE COLUMN: THE TRANSFORMATION */}
        <div className="md:col-span-4 flex flex-col justify-center space-y-8 py-4 relative z-0">
          
          <TransformationArrow 
            action="Productize" 
            desc="Raw data → SaaS Tools" 
            delay="0"
          />
          
          <TransformationArrow 
            action="Consolidate" 
            desc="Tactics → Solutions" 
            delay="100"
          />
          
          <TransformationArrow 
            action="Rebrand" 
            desc="Lists → Intelligence" 
            delay="200"
          />

          <TransformationArrow 
            action="Elevate" 
            desc="Departments → Ecosystem" 
            delay="300"
          />

        </div>

        {/* RIGHT COLUMN: FUTURE STATE */}
        <div className="md:col-span-4 relative group">
            {/* Glossy Background Effect */}
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-indigo-500/5 backdrop-blur-2xl rounded-2xl shadow-2xl border border-white/60 transition-all duration-500 group-hover:scale-[1.01] overflow-hidden">
                <div className="absolute -top-24 -right-24 w-64 h-64 bg-blue-400/20 rounded-full blur-3xl"></div>
                <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-indigo-400/20 rounded-full blur-3xl"></div>
            </div>

            <div className="relative p-8">
                <div className="flex items-center space-x-3 mb-6 border-b border-blue-100/50 pb-5">
                    <div className="bg-gradient-to-br from-blue-600 to-indigo-600 p-2.5 rounded-xl shadow-lg shadow-blue-500/30">
                    <Cpu className="w-5 h-5 text-white" />
                    </div>
                    <div>
                    <h2 className="font-bold text-slate-800 text-lg">Future State (2026)</h2>
                    <span className="inline-block mt-1 text-[10px] font-bold uppercase tracking-wider bg-blue-100 text-blue-700 px-2 py-0.5 rounded-md border border-blue-200">
                        The "Platform" Model
                    </span>
                    </div>
                </div>

                <div className="space-y-3">
                    <NavItem 
                    title="Platform / Products" 
                    subtext="Audience Builder, Intent Engine."
                    icon={<Cpu size={16} />}
                    theme="primary"
                    highlight
                    />
                    <NavItem 
                    title="Solutions" 
                    subtext="Growth Solutions, Creative."
                    icon={<BarChart size={16} />}
                    theme="primary"
                    />
                    <NavItem 
                    title="Data Intelligence" 
                    subtext="Enhancement, Management."
                    icon={<ShieldCheck size={16} />}
                    theme="primary"
                    />
                    <NavItem 
                    title="Global Execution (GCC)" 
                    subtext="Offshore Teams."
                    icon={<Globe size={16} />}
                    theme="secondary"
                    highlight
                    />
                    <NavItem 
                    title="Partnership" 
                    subtext="White-label, Resellers."
                    icon={<Briefcase size={16} />}
                    theme="secondary"
                    />
                    <NavItem 
                    title="Resources & About" 
                    subtext="Thought Leadership."
                    icon={<Layers size={16} />}
                    theme="primary"
                    />

                    <div className="mt-8 p-5 bg-emerald-50/80 rounded-xl border border-emerald-100 text-xs text-emerald-900 leading-relaxed shadow-sm backdrop-blur-sm">
                    <strong className="block mb-1 text-emerald-700 uppercase tracking-wide">Strategic Outcome</strong> 
                    Positioned as an indispensable Growth Ecosystem Partner.
                    </div>
                </div>
            </div>
        </div>
      </div>

      {/* SITEMAP DETAIL VIEW (CONDITIONAL) */}
      {activeView === 'sitemap' && (
        <div className="mt-12 p-8 bg-white/80 backdrop-blur-xl rounded-2xl border border-white/60 shadow-glass animate-[fadeIn_0.5s_ease-out]">
           <h3 className="font-bold text-xl text-slate-800 mb-8 border-b border-slate-100 pb-4">Detailed Navigation Tree <span className="text-blue-600 font-normal ml-2">2026 Proposal</span></h3>
           <div className="grid grid-cols-1 md:grid-cols-3 gap-10 text-sm">
              
              {/* Column 1 */}
              <div>
                <h4 className="font-bold text-slate-800 mb-4 flex items-center bg-blue-50 w-fit px-3 py-1.5 rounded-lg border border-blue-100">
                    <Cpu size={16} className="mr-2 text-blue-600"/> Platform / Products
                </h4>
                <ul className="space-y-3 pl-3">
                  {['Audience Builder', 'CRM Data Enrichment', 'Intent & Technographics', 'DSO Outreach Platform', 'Eyecare Outreach Platform', 'Growth Intelligence Platform'].map(item => (
                      <li key={item} className="flex items-center text-slate-600 hover:text-blue-600 transition-colors cursor-pointer group">
                          <div className="w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-blue-500 mr-2.5 transition-colors"></div>
                          {item}
                      </li>
                  ))}
                </ul>
              </div>

              {/* Column 2 */}
              <div>
                <h4 className="font-bold text-slate-800 mb-4 flex items-center bg-blue-50 w-fit px-3 py-1.5 rounded-lg border border-blue-100">
                    <BarChart size={16} className="mr-2 text-blue-600"/> Solutions
                </h4>
                <ul className="space-y-3 pl-3">
                  {['Growth Solutions', 'Campaign Solutions', 'Creative Intelligence', 'Demand Generation', 'Experience Design'].map(item => (
                      <li key={item} className="flex items-center text-slate-600 hover:text-blue-600 transition-colors cursor-pointer group">
                          <div className="w-1.5 h-1.5 rounded-full bg-slate-300 group-hover:bg-blue-500 mr-2.5 transition-colors"></div>
                          {item}
                      </li>
                  ))}
                </ul>
              </div>

               {/* Column 3 */}
               <div>
                <h4 className="font-bold text-slate-800 mb-4 flex items-center bg-blue-50 w-fit px-3 py-1.5 rounded-lg border border-blue-100">
                    <ShieldCheck size={16} className="mr-2 text-blue-600"/> Data Intelligence
                </h4>
                <ul className="space-y-4 pl-1">
                  <li className="text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100"><strong>Specialty Data:</strong> <span className="text-slate-500 block text-xs mt-1">B2B Marketing, Healthcare, Tech Installs, Investors...</span></li>
                  <li className="text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100"><strong>Data Management:</strong> <span className="text-slate-500 block text-xs mt-1">Enrichment, Profiling, Compliance...</span></li>
                  <li className="text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100"><strong>Data Enhancement:</strong> <span className="text-slate-500 block text-xs mt-1">Cleansing, Verification, Account Intel...</span></li>
                </ul>
              </div>

               {/* Row 2 - New Columns */}
               <div className="md:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-10 mt-2 pt-8 border-t border-slate-100/80">
                  <div>
                    <h4 className="font-bold text-slate-800 mb-4 flex items-center bg-indigo-50 w-fit px-3 py-1.5 rounded-lg border border-indigo-100">
                        <Globe size={16} className="mr-2 text-indigo-600"/> Global Execution (GCC)
                    </h4>
                    <ul className="space-y-3 pl-3">
                      <li className="text-slate-600 flex items-center"><div className="w-1.5 h-1.5 rounded-full bg-indigo-300 mr-2.5"></div>Offshore Team Setup</li>
                      <li className="text-slate-600 flex items-center"><div className="w-1.5 h-1.5 rounded-full bg-indigo-300 mr-2.5"></div>Global Operations Management</li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="font-bold text-slate-800 mb-4 flex items-center bg-indigo-50 w-fit px-3 py-1.5 rounded-lg border border-indigo-100">
                        <Briefcase size={16} className="mr-2 text-indigo-600"/> Partnership
                    </h4>
                    <ul className="space-y-3 pl-3">
                      <li className="text-slate-600 flex items-center"><div className="w-1.5 h-1.5 rounded-full bg-indigo-300 mr-2.5"></div>White-Label Programs</li>
                      <li className="text-slate-600 flex items-center"><div className="w-1.5 h-1.5 rounded-full bg-indigo-300 mr-2.5"></div>Reseller / Partner Programs</li>
                      <li className="text-slate-600 flex items-center"><div className="w-1.5 h-1.5 rounded-full bg-indigo-300 mr-2.5"></div>Data Licensing</li>
                    </ul>
                  </div>
               </div>

           </div>
        </div>
      )}

    </div>
  );
};

// Helper Component for Navigation Items
const NavItem = ({ title, subtext, icon, theme = 'muted', highlight }) => {
  
  let containerClasses = "group p-4 rounded-xl border flex items-start space-x-3 transition-all duration-300 ease-out hover:-translate-y-0.5";
  let iconClasses = "mt-1 transition-colors duration-300";
  let titleClasses = "font-bold text-sm transition-colors duration-300";
  let textClasses = "text-xs mt-1 leading-relaxed transition-colors duration-300";

  if (theme === 'muted') {
      containerClasses += " bg-white/50 border-slate-100 hover:bg-white hover:shadow-md hover:border-slate-200";
      iconClasses += " text-slate-400 group-hover:text-slate-600";
      titleClasses += " text-slate-600 group-hover:text-slate-800";
      textClasses += " text-slate-400 group-hover:text-slate-500";
  } else if (theme === 'primary') {
    containerClasses += highlight 
        ? " bg-gradient-to-br from-blue-600 to-blue-700 border-blue-500 shadow-lg shadow-blue-500/20 hover:shadow-blue-500/30"
        : " bg-white/60 border-blue-100 hover:bg-white hover:border-blue-200 hover:shadow-lg hover:shadow-blue-900/5";
    
    iconClasses += highlight ? " text-blue-100" : " text-blue-500 group-hover:text-blue-600";
    titleClasses += highlight ? " text-white" : " text-slate-700 group-hover:text-blue-900";
    textClasses += highlight ? " text-blue-100/80" : " text-slate-500";
  } else if (theme === 'secondary') {
    containerClasses += highlight
        ? " bg-gradient-to-br from-indigo-600 to-indigo-700 border-indigo-500 shadow-lg shadow-indigo-500/20 hover:shadow-indigo-500/30"
        : " bg-white/60 border-indigo-100 hover:bg-white hover:border-indigo-200 hover:shadow-lg hover:shadow-indigo-900/5";

    iconClasses += highlight ? " text-indigo-100" : " text-indigo-500 group-hover:text-indigo-600";
    titleClasses += highlight ? " text-white" : " text-slate-700 group-hover:text-indigo-900";
    textClasses += highlight ? " text-indigo-100/80" : " text-slate-500";
  }

  return (
    <div className={containerClasses}>
      <div className={iconClasses}>
        {icon}
      </div>
      <div>
        <h3 className={titleClasses}>{title}</h3>
        <p className={textClasses}>
          {subtext}
        </p>
      </div>
    </div>
  );
};

// Helper Component for Arrows
const TransformationArrow = ({ action, desc, delay }) => (
  <div className="flex items-center group w-full relative">
    {/* Animated Line */}
    <div className="hidden md:block h-0.5 bg-slate-200 w-full relative overflow-hidden rounded-full">
        <div className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-400 to-transparent w-1/2 -translate-x-full group-hover:animate-[shimmer_1.5s_infinite]"></div>
    </div>
    
    {/* Central Pill */}
    <div className="mx-4 flex flex-col items-center min-w-[140px] text-center z-10">
      <span className={`text-[11px] font-bold uppercase tracking-widest text-blue-600 bg-white px-4 py-1.5 rounded-full border border-blue-100 shadow-sm transition-all duration-300 group-hover:scale-110 group-hover:border-blue-300 group-hover:shadow-md group-hover:text-blue-700`}>
        {action}
      </span>
      <span className="text-[10px] text-slate-400 font-medium mt-2 max-w-[120px] leading-tight transition-colors group-hover:text-blue-400">
        {desc}
      </span>
    </div>
    
    {/* Animated Line Right */}
    <div className="hidden md:flex items-center w-full relative">
      <div className="h-0.5 bg-slate-200 w-full relative overflow-hidden rounded-full">
         <div className="absolute inset-0 bg-gradient-to-r from-transparent via-blue-400 to-transparent w-1/2 -translate-x-full group-hover:animate-[shimmer_1.5s_infinite] delay-75"></div>
      </div>
      <ArrowRight className="text-slate-300 w-4 h-4 -ml-2 transition-all duration-300 group-hover:text-blue-500 group-hover:translate-x-1" />
    </div>
  </div>
);

export default RoadmapVisualization;
