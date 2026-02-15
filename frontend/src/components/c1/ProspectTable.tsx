interface Prospect {
  email: string;
  name?: string;
  company?: string;
  title?: string;
  industry?: string;
}

interface ProspectTableProps {
  prospects: Prospect[];
}

export function ProspectTable({ prospects }: ProspectTableProps) {
  if (!prospects.length) {
    return <p className="text-sm text-slate-500 py-4 text-center">No prospects to display.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            <th className="px-4 py-3 text-left font-medium text-slate-600">Email</th>
            <th className="px-4 py-3 text-left font-medium text-slate-600">Name</th>
            <th className="px-4 py-3 text-left font-medium text-slate-600">Company</th>
            <th className="px-4 py-3 text-left font-medium text-slate-600">Title</th>
            <th className="px-4 py-3 text-left font-medium text-slate-600">Industry</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {prospects.map((p, i) => (
            <tr key={i} className="hover:bg-slate-50 transition-colors">
              <td className="px-4 py-3 text-brand-purple font-medium">{p.email}</td>
              <td className="px-4 py-3 text-slate-700">{p.name || '-'}</td>
              <td className="px-4 py-3 text-slate-700">{p.company || '-'}</td>
              <td className="px-4 py-3 text-slate-500">{p.title || '-'}</td>
              <td className="px-4 py-3 text-slate-500">{p.industry || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
