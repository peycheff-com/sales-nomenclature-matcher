import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Pencil, X, Search, Loader2 } from "lucide-react";
import { reviewItem } from "@/api/review";
import { searchCatalog } from "@/api/catalog";
import type { MatchResult, ReviewInput } from "@/api/types";
import { DECISION_LABELS, DECISION_COLORS } from "@/lib/constants";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";

interface ReviewActionsProps {
  item: MatchResult;
  onReviewed: (decision: string) => void;
}

export default function ReviewActions({ item, onReviewed }: ReviewActionsProps) {
  const [correcting, setCorrecting] = useState(false);
  const [isOverriding, setIsOverriding] = useState(false);
  const [correctedProductId, setCorrectedProductId] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchTrigger, setSearchTrigger] = useState("");

  const catalogQuery = useQuery({
    queryKey: ["catalog-search", searchTrigger],
    queryFn: () => searchCatalog(searchTrigger, 10),
    enabled: searchTrigger.length > 0,
  });

  const mutation = useMutation({
    mutationFn: (input: ReviewInput) =>
      reviewItem(item.request_item_id, input),
    onSuccess: (_, variables) => {
      setCorrecting(false);
      setIsOverriding(false);
      toast.success("Решение сохранено");
      onReviewed(variables.final_decision);
    },
    onError: () => {
      toast.error("Ошибка сохранения решения");
    }
  });

  function handleAccept() {
    mutation.mutate({
      final_decision: "accepted",
      final_product_id: item.best_candidate?.product_id,
      create_supplier_mapping: true,
    });
  }

  function handleReject() {
    mutation.mutate({
      final_decision: "rejected",
    });
  }

  function handleCorrect() {
    mutation.mutate({
      final_decision: "corrected",
      final_product_id: correctedProductId || undefined,
      create_alias: true,
      create_supplier_mapping: true,
    });
  }

  if (item.status === "auto_match" && !item.final_decision && !isOverriding) {
    return (
      <>
        <div className="flex flex-col gap-0.5 relative group">
          <span className="text-xs text-green-600 font-medium">Авто</span>
          <div className="absolute right-0 top-0 opacity-60 hover:opacity-100 transition-opacity flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px] text-green-700 hover:text-green-800"
              onClick={handleAccept}
              disabled={mutation.isPending}
              title="Подтвердить авто-сопоставление"
            >
              <Check className="h-3 w-3 mr-0.5" />
              Ок
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px] text-yellow-700 hover:text-yellow-800"
              onClick={() => { setSearchQuery(item.raw_text); setSearchTrigger(item.raw_text); setCorrecting(true); }}
              disabled={mutation.isPending}
              title="Исправить авто-сопоставление"
            >
              <Pencil className="h-3 w-3 mr-0.5" />
              Исправить
            </Button>
          </div>
        </div>

        <Dialog open={correcting} onOpenChange={setCorrecting}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Указать правильный товар</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-2">
              <div className="rounded bg-muted p-2 text-sm">
                <span className="font-semibold">Исходный текст:</span> {item.raw_text}
              </div>
              <div className="space-y-1.5 flex flex-col gap-2">
                <Label>Поиск по каталогу (название, артикул, бренд)</Label>
                <div className="flex gap-2">
                  <Input
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        setSearchTrigger(searchQuery);
                      }
                    }}
                    placeholder="Введите запрос и нажмите Enter"
                  />
                  <Button variant="secondary" onClick={() => setSearchTrigger(searchQuery)} disabled={catalogQuery.isFetching}>
                    {catalogQuery.isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <div className="max-h-[300px] overflow-y-auto border border-border rounded-md mt-4">
                {catalogQuery.isLoading && <div className="p-4 text-center text-sm text-muted-foreground">Загрузка...</div>}
                {catalogQuery.isSuccess && catalogQuery.data.length === 0 && <div className="p-4 text-center text-sm text-muted-foreground">Ничего не найдено</div>}
                {catalogQuery.isSuccess && catalogQuery.data.length > 0 && (
                  <div className="divide-y divide-border">
                    {catalogQuery.data.map((product) => (
                      <div
                        key={product.product_id}
                        className={`p-3 text-sm cursor-pointer hover:bg-muted/50 transition-colors ${correctedProductId === product.product_id ? 'bg-primary/10 border-l-2 border-l-primary' : ''}`}
                        onClick={() => setCorrectedProductId(product.product_id)}
                      >
                        <div className="font-medium">{product.name}</div>
                        <div className="text-xs text-muted-foreground mt-1 flex justify-between">
                          <span>Арт: {product.article || "\u2014"}</span>
                          <span>Бренд: {product.brand || "\u2014"}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {correctedProductId && (
                <div className="bg-green-50 text-green-800 text-xs p-2 rounded border border-green-200">
                  Выбран товар: {correctedProductId}
                </div>
              )}
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setCorrecting(false)}>
                Отмена
              </Button>
              <Button onClick={handleCorrect} disabled={mutation.isPending || !correctedProductId}>
                Сохранить
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </>
    );
  }

  if (item.final_decision && !isOverriding) {
    return (
      <div className="flex flex-col gap-0.5 relative group">
        <span className={`text-xs font-medium px-2 py-0.5 rounded border max-w-max ${DECISION_COLORS[item.final_decision]}`}>
          {DECISION_LABELS[item.final_decision] ?? item.final_decision}
        </span>
        {item.reviewed_by && (
          <span className="text-[10px] text-muted-foreground">{item.reviewed_by}</span>
        )}
        <div className="absolute right-0 top-0 opacity-60 hover:opacity-100 transition-opacity">
          <Button 
            variant="outline" 
            size="icon" 
            className="h-6 w-6 rounded-full bg-background/80 backdrop-blur-sm text-muted-foreground hover:text-foreground" 
            onClick={() => setIsOverriding(true)} 
            title="Изменить решение"
          >
            <Pencil className="h-3 w-3" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs text-green-700 hover:text-green-800"
          onClick={handleAccept}
          disabled={mutation.isPending || !item.best_candidate}
          title="Подтвердить лучший результат"
        >
          <Check className="h-3.5 w-3.5" />
          Ок
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs text-yellow-700 hover:text-yellow-800"
          onClick={() => { setSearchQuery(item.raw_text); setSearchTrigger(item.raw_text); setCorrecting(true); }}
          disabled={mutation.isPending}
          title="Указать правильный товар"
        >
          <Pencil className="h-3.5 w-3.5" />
          Исправить
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1 text-xs text-red-700 hover:text-red-800"
          onClick={handleReject}
          disabled={mutation.isPending}
          title="Отклонить"
        >
          <X className="h-3.5 w-3.5" />
          Нет
        </Button>
        {isOverriding && (
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-muted-foreground ml-1 bg-muted/50"
            onClick={() => setIsOverriding(false)}
            title="Отменить изменение"
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      <Dialog open={correcting} onOpenChange={setCorrecting}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Указать правильный товар</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="rounded bg-muted p-2 text-sm">
              <span className="font-semibold">Исходный текст:</span> {item.raw_text}
            </div>
            <div className="space-y-1.5 flex flex-col gap-2">
              <Label>Поиск по каталогу (название, артикул, бренд)</Label>
              <div className="flex gap-2">
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      setSearchTrigger(searchQuery);
                    }
                  }}
                  placeholder="Введите запрос и нажмите Enter"
                />
                <Button variant="secondary" onClick={() => setSearchTrigger(searchQuery)} disabled={catalogQuery.isFetching}>
                  {catalogQuery.isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                </Button>
              </div>
            </div>
            
            <div className="max-h-[300px] overflow-y-auto border border-border rounded-md mt-4">
              {catalogQuery.isLoading && <div className="p-4 text-center text-sm text-muted-foreground">Загрузка...</div>}
              {catalogQuery.isSuccess && catalogQuery.data.length === 0 && <div className="p-4 text-center text-sm text-muted-foreground">Ничего не найдено</div>}
              {catalogQuery.isSuccess && catalogQuery.data.length > 0 && (
                <div className="divide-y divide-border">
                  {catalogQuery.data.map((product) => (
                    <div 
                      key={product.product_id}
                      className={`p-3 text-sm cursor-pointer hover:bg-muted/50 transition-colors ${correctedProductId === product.product_id ? 'bg-primary/10 border-l-2 border-l-primary' : ''}`}
                      onClick={() => setCorrectedProductId(product.product_id)}
                    >
                      <div className="font-medium">{product.name}</div>
                      <div className="text-xs text-muted-foreground mt-1 flex justify-between">
                        <span>Арт: {product.article || "—"}</span>
                        <span>Бренд: {product.brand || "—"}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {correctedProductId && (
              <div className="bg-green-50 text-green-800 text-xs p-2 rounded border border-green-200">
                Выбран товар: {correctedProductId}
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCorrecting(false)}>
              Отмена
            </Button>
            <Button onClick={handleCorrect} disabled={mutation.isPending || !correctedProductId}>
              Сохранить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
