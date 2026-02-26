import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Users,
  Mail,
  FileText,
  Settings,
  LogOut,
  Zap,
  Bot,
  Globe,
  Send,
  BarChart3,
  Sparkles,
  Upload,
  Link2,
  Network,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { clsx } from 'clsx';

const mainNavigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, tourId: 'nav-dashboard' },
  { name: 'Prospects', href: '/prospects', icon: Users, tourId: 'nav-prospects' },
  { name: 'Campaigns', href: '/campaigns', icon: Mail, tourId: 'nav-campaigns' },
  { name: 'Sequences', href: '/sequences', icon: Zap, tourId: 'nav-sequences' },
  { name: 'Templates', href: '/templates', icon: FileText, tourId: 'nav-templates' },
  { name: 'Knowledge Graph', href: '/graph', icon: Network, tourId: 'nav-graph' },
  { name: 'Analytics', href: '/analytics', icon: BarChart3, tourId: 'nav-analytics' },
];

const aiNavigation = [
  { name: 'AI Assistant', href: '/assistant', icon: Bot, tourId: 'nav-assistant' },
  { name: 'AI Campaign Builder', href: '/ai-campaigns', icon: Sparkles, tourId: 'nav-ai-campaigns' },
];

const toolsNavigation = [
  { name: 'Domains', href: '/domains', icon: Globe, tourId: 'nav-domains' },
  { name: 'UTM Manager', href: '/utm', icon: Link2, tourId: 'nav-utm' },
  { name: 'Test Console', href: '/send', icon: Send, tourId: 'nav-send' },
  { name: 'Workflows', href: '/workflows', icon: Zap, tourId: 'nav-workflows' },
];

const adminNavigation = [
  { name: 'Prospect Lists', href: '/admin/prospect-lists', icon: Upload, tourId: 'nav-admin-lists' },
];

export function Sidebar() {
  const location = useLocation();
  const { logout, user } = useAuthStore();

  const renderLink = (item: any) => {
    const isActive = location.pathname === item.href ||
      (item.href !== '/' && location.pathname.startsWith(item.href));

    return (
      <Link
        key={item.name}
        to={item.href}
        data-tour={item.tourId}
        className={clsx(
          'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors',
          isActive
            ? 'bg-brand-purple text-white'
            : 'text-slate-300 hover:bg-white/10 hover:text-white'
        )}
      >
        <item.icon className="h-4 w-4" />
        {item.name}
      </Link>
    );
  };

  return (
    <div className="flex h-full w-64 flex-col bg-brand-navy" data-tour="sidebar">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-6 border-b border-white/10">
        <Mail className="h-8 w-8 text-brand-gold" />
        <span className="text-xl font-bold text-white">ChampMail</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-6 px-3 py-4 overflow-y-auto">
        <div>
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-3 mb-2">Main</p>
          <div className="space-y-1">
            {mainNavigation.map(renderLink)}
          </div>
        </div>

        <div>
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-3 mb-2">AI Tools</p>
          <div className="space-y-1">
            {aiNavigation.map(renderLink)}
          </div>
        </div>

        <div>
          <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-3 mb-2">Tools & Setup</p>
          <div className="space-y-1">
            {toolsNavigation.map(renderLink)}
          </div>
        </div>

        {/* Admin section - only for admin/data_team roles */}
        {(user?.role === 'admin' || user?.role === 'data_team') && (
          <div>
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-3 mb-2">Admin</p>
            <div className="space-y-1">
              {adminNavigation.map(renderLink)}
            </div>
          </div>
        )}
      </nav>

      {/* User section */}
      <div className="border-t border-white/10 p-4">
        <div className="flex items-center justify-between mb-4">
          <Link
            to="/settings"
            data-tour="nav-settings"
            className={clsx(
              'flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors w-full',
              location.pathname.startsWith('/settings')
                ? 'bg-brand-purple text-white'
                : 'text-slate-300 hover:bg-white/10 hover:text-white'
            )}
          >
            <Settings className="h-4 w-4" />
            Settings
          </Link>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-brand-purple text-sm font-medium text-white">
            {user?.email?.charAt(0).toUpperCase() || 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">
              {user?.full_name || user?.email || 'User'}
            </p>
            <p className="text-xs text-slate-400 truncate">{user?.email}</p>
          </div>
          <button
            onClick={logout}
            className="p-2 text-slate-400 hover:text-white hover:bg-white/10 rounded-lg transition-colors"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

export default Sidebar;
