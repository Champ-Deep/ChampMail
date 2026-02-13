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
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { clsx } from 'clsx';

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, tourId: 'nav-dashboard' },
  { name: 'AI Campaign Builder', href: '/ai-campaigns', icon: Sparkles, tourId: 'nav-ai-campaigns' },
  { name: 'Prospects', href: '/prospects', icon: Users, tourId: 'nav-prospects' },
  { name: 'Sequences', href: '/sequences', icon: Zap, tourId: 'nav-sequences' },
  { name: 'Templates', href: '/templates', icon: FileText, tourId: 'nav-templates' },
  { name: 'Campaigns', href: '/campaigns', icon: Mail, tourId: 'nav-campaigns' },
  { name: 'Domains', href: '/domains', icon: Globe, tourId: 'nav-domains' },
  { name: 'Send Console', href: '/send', icon: Send, tourId: 'nav-send' },
  { name: 'Analytics', href: '/analytics', icon: BarChart3, tourId: 'nav-analytics' },
  { name: 'Workflows', href: '/workflows', icon: Bot, tourId: 'nav-workflows' },
  { name: 'Settings', href: '/settings', icon: Settings, tourId: 'nav-settings' },
];

const adminNavigation = [
  { name: 'Prospect Lists', href: '/admin/prospect-lists', icon: Upload, tourId: 'nav-admin-lists' },
];

export function Sidebar() {
  const location = useLocation();
  const { logout, user } = useAuthStore();

  return (
    <div className="flex h-full w-64 flex-col bg-slate-900" data-tour="sidebar">
      {/* Logo */}
      <div className="flex h-16 items-center gap-2 px-6 border-b border-slate-700">
        <Mail className="h-8 w-8 text-blue-500" />
        <span className="text-xl font-bold text-white">ChampMail</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4 overflow-y-auto">
        {navigation.map((item) => {
          const isActive = location.pathname === item.href ||
            (item.href !== '/' && location.pathname.startsWith(item.href));

          return (
            <Link
              key={item.name}
              to={item.href}
              data-tour={item.tourId}
              className={clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              )}
            >
              <item.icon className="h-5 w-5" />
              {item.name}
            </Link>
          );
        })}

        {/* Admin section - only for admin/data_team roles */}
        {(user?.role === 'admin' || user?.role === 'data_team') && (
          <>
            <div className="pt-4 pb-1 px-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Admin</p>
            </div>
            {adminNavigation.map((item) => {
              const isActive = location.pathname.startsWith(item.href);
              return (
                <Link
                  key={item.name}
                  to={item.href}
                  data-tour={item.tourId}
                  className={clsx(
                    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                  )}
                >
                  <item.icon className="h-5 w-5" />
                  {item.name}
                </Link>
              );
            })}
          </>
        )}
      </nav>

      {/* User section */}
      <div className="border-t border-slate-700 p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-blue-600 text-sm font-medium text-white">
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
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
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
