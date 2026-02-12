import { clsx } from 'clsx';
import { type InputHTMLAttributes, forwardRef } from 'react';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helperText, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-sm font-medium text-slate-700 mb-1.5"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx(
            'w-full h-10 px-3 rounded-lg border bg-white text-sm outline-none transition-colors',
            'placeholder:text-slate-400',
            'focus:ring-2 focus:ring-offset-0',
            error
              ? 'border-red-300 focus:border-red-500 focus:ring-red-200'
              : 'border-slate-300 focus:border-blue-500 focus:ring-blue-200',
            'disabled:bg-slate-50 disabled:text-slate-500 disabled:cursor-not-allowed',
            className
          )}
          {...props}
        />
        {(error || helperText) && (
          <p
            className={clsx(
              'mt-1.5 text-sm',
              error ? 'text-red-600' : 'text-slate-500'
            )}
          >
            {error || helperText}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export default Input;
