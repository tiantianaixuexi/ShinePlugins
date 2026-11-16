import { Toaster as Sonner, type ToasterProps } from "sonner";

/**
 * Sonner toaster bound to the active theme.
 *
 * Theme is read from the `dark` class so the toast follows the same switch as
 * the rest of the shell without a React context.
 */
function Toaster(props: ToasterProps) {
  const isDark =
    typeof document !== "undefined" && document.documentElement.classList.contains("dark");

  return (
    <Sonner
      theme={isDark ? "dark" : "light"}
      className="toaster group"
      position="bottom-right"
      offset={24}
      toastOptions={{
        classNames: {
          toast: "group toast font-sans",
          description: "text-muted-foreground",
          actionButton: "bg-primary text-primary-foreground",
          cancelButton: "bg-muted text-muted-foreground",
          error: "text-destructive",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };