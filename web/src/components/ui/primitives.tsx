import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

import { cn } from "../../lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md";

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-ink dark:text-canvas dark:hover:bg-accent-ink border border-transparent",
  secondary: "bg-surface text-ink border border-control hover:border-ink",
  ghost: "text-muted hover:text-ink hover:bg-subtle border border-transparent",
  danger: "bg-bad text-white hover:bg-bad/90 border border-transparent",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  md: "h-8 px-3 text-sm gap-2",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      disabled={disabled || loading}
      className={cn(
        "inline-flex shrink-0 items-center justify-center whitespace-nowrap rounded font-medium transition-colors",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
});

const FIELD = "rounded border border-control bg-surface text-sm text-ink placeholder:text-faint hover:border-ink focus:border-accent";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cn("h-8 w-full px-2.5", FIELD, className)} {...rest} />;
});

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(function Select(
  { className, children, ...rest },
  ref,
) {
  return (
    <select ref={ref} className={cn("h-8 pl-2.5 pr-7", FIELD, className)} {...rest}>
      {children}
    </select>
  );
});

/** A bordered surface. Layout uses hairlines, not shadows; only overlays float. */
export function Panel({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border border-line bg-surface", className)} {...rest} />;
}

/** Small-caps label that opens a section of a page or pane. */
export function SectionLabel({ children, count, className, ...rest }: HTMLAttributes<HTMLParagraphElement> & { count?: ReactNode }) {
  return (
    <p className={cn("caps", className)} {...rest}>
      {children}
      {count !== undefined && <span className="num ml-1.5 font-mono normal-case tracking-normal text-faint">{count}</span>}
    </p>
  );
}

type Tone = "neutral" | "accent" | "ok" | "warn" | "bad";

const TONES: Record<Tone, string> = {
  neutral: "bg-subtle text-ink border-line",
  accent: "bg-accent-soft text-accent-ink border-line",
  ok: "bg-ok-soft text-ok border-line",
  warn: "bg-warn-soft text-warn border-line",
  bad: "bg-bad-soft text-bad border-line",
};

export function Tag({ tone = "neutral", className, children, ...rest }: HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return (
    <span
      className={cn("inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 text-2xs font-medium", TONES[tone], className)}
      {...rest}
    >
      {children}
    </span>
  );
}

export interface SegmentedItem<T extends string> {
  value: T;
  label: ReactNode;
  count?: number;
}

/** A row of exclusive options in one hairline frame; the pressed one is ink on paper. */
export function Segmented<T extends string>({
  items,
  value,
  onChange,
  size = "md",
  ...rest
}: { items: SegmentedItem<T>[]; value: T; onChange: (v: T) => void; size?: Size } & Omit<HTMLAttributes<HTMLDivElement>, "onChange">) {
  return (
    <div role="group" className="inline-flex overflow-hidden rounded border border-control text-xs font-medium" {...rest}>
      {items.map((item, i) => {
        const pressed = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            aria-pressed={pressed}
            onClick={() => onChange(item.value)}
            className={cn(
              "flex items-center gap-1.5 px-2.5",
              size === "sm" ? "h-6" : "h-7",
              i > 0 && "border-l border-control",
              pressed ? "bg-ink text-canvas" : "bg-surface text-muted hover:text-ink",
            )}
          >
            {item.label}
            {item.count !== undefined && <span className={cn("num font-mono", pressed ? "opacity-80" : "text-faint")}>{item.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export function Dot({ tone, hollow }: { tone: Tone; hollow?: boolean }) {
  const color = { neutral: "bg-faint", accent: "bg-accent", ok: "bg-ok", warn: "bg-warn", bad: "bg-bad" }[tone];
  return (
    <span
      className={cn("inline-block size-1.5 shrink-0 rounded-full", hollow ? "border border-faint bg-transparent" : color)}
      aria-hidden
    />
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-sm border border-line bg-subtle px-1 font-mono text-[10.5px] text-muted">
      {children}
    </kbd>
  );
}

/** A static two-tone placeholder in the shape of the content it stands in for. */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("rounded-sm bg-subtle", className)} aria-hidden />;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin text-muted", className)} aria-label="Loading" />;
}

export type { Tone };
