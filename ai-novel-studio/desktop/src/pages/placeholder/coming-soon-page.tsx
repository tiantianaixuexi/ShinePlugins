import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Construction, Lock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { findNavItem } from "@/config/navigation";

/**
 * Placeholder for modules that exist in the navigation but are not built yet.
 * It names the milestone and the planned capabilities so the gap is explicit
 * instead of a blank screen.
 */
export function ComingSoonPage() {
  const { pathname } = useLocation();
  const item = findNavItem(pathname);
  const Icon = item?.icon ?? Construction;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 p-6">
      <Card className="studio-grid overflow-hidden">
        <CardContent className="flex flex-col items-center gap-4 py-14 text-center">
          <div className="grid size-14 place-items-center rounded-2xl border bg-background shadow-sm">
            <Icon className="size-6 text-muted-foreground" />
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-semibold tracking-tight">{item?.label ?? "模块"}</h2>
            <p className="max-w-md text-sm text-muted-foreground">
              {item?.description ?? "该模块尚未开始实现。"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="warning">{item?.milestone ?? "规划中"} 交付</Badge>
            <Badge variant="outline" className="gap-1">
              <Construction className="size-3" />
              开发中
            </Badge>
          </div>
          <Button asChild variant="outline" size="sm">
            <Link to="/">
              返回工作台
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </CardContent>
      </Card>

      {item?.features?.length ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">计划能力</CardTitle>
            <CardDescription>该模块进入开发后会依次交付：</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="grid gap-2 sm:grid-cols-2">
              {item.features.map((feature) => (
                <li
                  key={feature}
                  className="flex items-start gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground"
                >
                  <Lock className="mt-0.5 size-3.5 shrink-0" />
                  <span>{feature}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}