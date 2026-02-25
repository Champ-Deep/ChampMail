import type { ReactNode } from 'react';
import { Sparkles } from 'lucide-react';

interface ComingSoonWrapperProps {
  children: ReactNode;
  title: string;
  description: string;
}

export function ComingSoonWrapper({ children, title, description }: ComingSoonWrapperProps) {
  return (
    <div className="relative min-h-[calc(100vh-4rem)] bg-slate-50 overflow-hidden rounded-lg">
      {/* Dimmed background content */}
      <div className="absolute inset-0 opacity-20 pointer-events-none filter blur-[2px] transition-all duration-500">
        {children}
      </div>

      {/* Overlay banner */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-auto bg-slate-50/60 backdrop-blur-sm z-10">
        <div className="bg-white p-8 rounded-2xl shadow-xl max-w-md w-full text-center border border-slate-100 transform transition-all hover:scale-105 duration-300">
          <div className="mx-auto w-16 h-16 bg-brand-purple/10 rounded-full flex items-center justify-center mb-6">
            <Sparkles className="h-8 w-8 text-brand-purple" />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mb-3">{title}</h2>
          <p className="text-slate-600 mb-8">{description}</p>
          
          <button className="inline-flex items-center justify-center px-6 py-3 border border-transparent text-sm font-medium rounded-lg text-brand-purple bg-brand-purple/10 hover:bg-brand-purple/20 transition-colors">
            Join the Waitlist
          </button>
        </div>
      </div>
    </div>
  );
}
