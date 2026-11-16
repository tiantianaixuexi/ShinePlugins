import { Link } from "react-router-dom";
import { Compass } from "lucide-react";

import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="grid size-12 place-items-center rounded-xl border">
        <Compass className="size-5 text-muted-foreground" />
      </div>
      <h2 className="text-lg font-semibold">页面不存在</h2>
      <p className="text-sm text-muted-foreground">该地址可能已经移动，或者从未存在过。</p>
      <Button asChild variant="outline" size="sm">
        <Link to="/">返回工作台</Link>
      </Button>
    </div>
  );
}