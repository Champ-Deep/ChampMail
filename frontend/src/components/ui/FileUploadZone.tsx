import { useState, useCallback, useRef } from 'react';
import { Upload, FileSpreadsheet, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { clsx } from 'clsx';
import { Button } from './Button';

interface FileUploadZoneProps {
  onFileSelected: (file: File) => void;
  isUploading: boolean;
}

export function FileUploadZone({ onFileSelected, isUploading }: FileUploadZoneProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragOver(false);

      const files = e.dataTransfer.files;
      if (files.length > 0) {
        const file = files[0];
        if (
          file.type === 'text/csv' ||
          file.name.endsWith('.csv') ||
          file.type ===
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' ||
          file.name.endsWith('.xlsx')
        ) {
          onFileSelected(file);
        } else {
          toast.error('Please upload a CSV or XLSX file');
        }
      }
    },
    [onFileSelected]
  );

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        onFileSelected(file);
      }
      // Reset input so same file can be selected again
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    },
    [onFileSelected]
  );

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={clsx(
        'relative border-2 border-dashed rounded-xl p-10 text-center transition-all duration-200 cursor-pointer',
        isDragOver
          ? 'border-brand-purple/70 bg-brand-purple/5 scale-[1.01]'
          : 'border-slate-300 bg-slate-50 hover:border-slate-400 hover:bg-white'
      )}
      onClick={() => fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv,.xlsx"
        onChange={handleFileInput}
        className="hidden"
      />

      {isUploading ? (
        <div className="flex flex-col items-center">
          <Loader2 className="h-10 w-10 text-brand-purple animate-spin mb-3" />
          <p className="text-sm font-medium text-slate-700">
            Uploading prospect list...
          </p>
          <p className="text-xs text-slate-500 mt-1">
            This may take a moment for large files
          </p>
        </div>
      ) : (
        <div className="flex flex-col items-center">
          <div className="h-14 w-14 rounded-full bg-brand-purple/10 flex items-center justify-center mb-4">
            <Upload className="h-6 w-6 text-brand-purple" />
          </div>
          <p className="text-sm font-medium text-slate-700 mb-1">
            {isDragOver
              ? 'Drop your file here'
              : 'Drag and drop your CSV file here'}
          </p>
          <p className="text-xs text-slate-500 mb-4">or click to browse</p>
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              fileInputRef.current?.click();
            }}
          >
            <FileSpreadsheet className="h-4 w-4 mr-1.5" />
            Browse Files
          </Button>
          <p className="text-xs text-slate-400 mt-4">
            Accepted: .csv, .xlsx -- Required column: email
          </p>
        </div>
      )}
    </div>
  );
}
