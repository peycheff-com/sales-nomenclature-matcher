import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Loader2, KeyRound, UserCog, Copy, Check } from "lucide-react";
import { toast } from "sonner";
import {
  listUsers,
  createUser,
  updateUser,
  resetUserPassword,
  type UserDetail,
  type UserCreateInput,
} from "@/api/users";
import { getMe } from "@/api/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { PageLayout } from "@/components/layout/page-layout";

const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  operator: "Оператор",
  viewer: "Наблюдатель",
};

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-purple-50 text-purple-700",
  operator: "bg-blue-50 text-blue-700",
  viewer: "bg-gray-50 text-gray-700",
};

function generatePassword(): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";
  let result = "";
  for (let i = 0; i < 12; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

export default function UsersPage() {
  const queryClient = useQueryClient();

  // State for create dialog
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [newFullName, setNewFullName] = useState("");
  const [newRole, setNewRole] = useState<"admin" | "operator" | "viewer">("operator");
  const [newPassword, setNewPassword] = useState("");
  const [copied, setCopied] = useState(false);

  // State for edit dialog
  const [editTarget, setEditTarget] = useState<UserDetail | null>(null);
  const [editFullName, setEditFullName] = useState("");
  const [editRole, setEditRole] = useState<"admin" | "operator" | "viewer">("operator");

  // State for reset password dialog
  const [resetTarget, setResetTarget] = useState<UserDetail | null>(null);
  const [resetPassword, setResetPassword] = useState("");

  // State for deactivation confirmation
  const [deactivateTarget, setDeactivateTarget] = useState<UserDetail | null>(null);

  const meQuery = useQuery({ queryKey: ["me"], queryFn: getMe, retry: false });
  const usersQuery = useQuery({ queryKey: ["users"], queryFn: listUsers });

  const createMutation = useMutation({
    mutationFn: (input: UserCreateInput) => createUser(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setIsCreateOpen(false);
      resetCreateForm();
      toast.success("Пользователь создан");
    },
    onError: (err: unknown) => {
      const msg =
        err && typeof err === "object" && "response" in err
          ? "Имя пользователя уже занято"
          : "Ошибка при создании пользователя";
      toast.error(msg);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ userId, ...data }: { userId: string; full_name?: string; role?: string; is_active?: boolean }) =>
      updateUser(userId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditTarget(null);
      toast.success("Изменения сохранены");
    },
    onError: () => toast.error("Ошибка при сохранении"),
  });

  const resetPasswordMutation = useMutation({
    mutationFn: ({ userId, password }: { userId: string; password: string }) =>
      resetUserPassword(userId, password),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setResetTarget(null);
      setResetPassword("");
      toast.success("Пароль сброшен. Пользователю потребуется сменить пароль при следующем входе.");
    },
    onError: () => toast.error("Ошибка при сбросе пароля"),
  });

  function resetCreateForm() {
    setNewUsername("");
    setNewFullName("");
    setNewRole("operator");
    setNewPassword("");
    setCopied(false);
  }

  function handleGeneratePassword() {
    const pw = generatePassword();
    setNewPassword(pw);
    navigator.clipboard.writeText(pw).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success("Пароль скопирован в буфер обмена");
    });
  }

  function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!newUsername || !newPassword) {
      toast.error("Заполните обязательные поля");
      return;
    }
    createMutation.mutate({
      username: newUsername,
      full_name: newFullName || undefined,
      role: newRole,
      password: newPassword,
    });
  }

  function openEditDialog(user: UserDetail) {
    setEditTarget(user);
    setEditFullName(user.full_name ?? "");
    setEditRole(user.role as "admin" | "operator" | "viewer");
  }

  function handleEditSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!editTarget) return;
    updateMutation.mutate({
      userId: editTarget.user_id,
      full_name: editFullName || undefined,
      role: editRole,
    });
  }

  function handleToggleActive(user: UserDetail, val: boolean) {
    if (!val) {
      setDeactivateTarget(user);
    } else {
      updateMutation.mutate({ userId: user.user_id, is_active: true });
    }
  }

  function openResetDialog(user: UserDetail) {
    setResetTarget(user);
    const pw = generatePassword();
    setResetPassword(pw);
  }

  const users = usersQuery.data?.items ?? [];
  const currentUserId = meQuery.data?.user_id;

  return (
    <PageLayout
      title="Пользователи"
      description="Создание, редактирование и управление учётными записями."
      actions={
        <Dialog
          open={isCreateOpen}
          onOpenChange={(open) => {
            setIsCreateOpen(open);
            if (!open) resetCreateForm();
          }}
        >
          <DialogTrigger className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow hover:bg-primary/90 h-9 px-4 py-2">
            <Plus className="mr-2 h-4 w-4" />
            Создать пользователя
          </DialogTrigger>
          <DialogContent>
            <form onSubmit={handleCreateSubmit}>
              <DialogHeader>
                <DialogTitle>Новый пользователь</DialogTitle>
                <DialogDescription>
                  Создайте учётную запись. Пользователю потребуется сменить пароль при первом входе.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid gap-2">
                  <Label htmlFor="create-username">Имя пользователя</Label>
                  <Input
                    id="create-username"
                    placeholder="ivanov"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    autoComplete="off"
                  />
                  <p className="text-[10px] text-muted-foreground">
                    Латиница, цифры, подчёркивания. Нельзя изменить позже.
                  </p>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="create-fullname">Полное имя</Label>
                  <Input
                    id="create-fullname"
                    placeholder="Иванов Иван Иванович"
                    value={newFullName}
                    onChange={(e) => setNewFullName(e.target.value)}
                  />
                </div>
                <div className="grid gap-2">
                  <Label>Роль</Label>
                  <Select value={newRole} onValueChange={(v) => setNewRole(v as typeof newRole)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admin">Администратор</SelectItem>
                      <SelectItem value="operator">Оператор</SelectItem>
                      <SelectItem value="viewer">Наблюдатель</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid gap-2">
                  <Label htmlFor="create-password">Временный пароль</Label>
                  <div className="flex gap-2">
                    <Input
                      id="create-password"
                      type="text"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      placeholder="Минимум 6 символов"
                      autoComplete="off"
                    />
                    <Button type="button" variant="outline" size="sm" onClick={handleGeneratePassword}>
                      {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                  <p className="text-[10px] text-muted-foreground">
                    Нажмите кнопку для генерации и копирования пароля.
                  </p>
                </div>
              </div>
              <DialogFooter>
                <Button variant="outline" type="button" onClick={() => setIsCreateOpen(false)}>
                  Отмена
                </Button>
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Создать
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      }
    >
      <Card>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Пользователь</TableHead>
                <TableHead>Роль</TableHead>
                <TableHead>Статус</TableHead>
                <TableHead>Создан</TableHead>
                <TableHead className="text-right w-32">Действия</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usersQuery.isLoading ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-24 text-center">
                    <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ) : users.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                    Нет пользователей
                  </TableCell>
                </TableRow>
              ) : (
                users.map((u) => (
                  <TableRow key={u.user_id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <UserCog className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <div className="font-medium text-sm">
                            {u.full_name || u.username}
                          </div>
                          {u.full_name && (
                            <div className="text-xs text-muted-foreground">
                              @{u.username}
                            </div>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={ROLE_COLORS[u.role] ?? ""}>
                        {ROLE_LABELS[u.role] ?? u.role}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={u.is_active}
                          disabled={u.user_id === currentUserId}
                          onCheckedChange={(val) => handleToggleActive(u, val)}
                        />
                        <Badge
                          variant="outline"
                          className={
                            u.is_active
                              ? "bg-green-50 text-green-700"
                              : "bg-gray-50 text-gray-700"
                          }
                        >
                          {u.is_active ? "Активен" : "Отключён"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {new Date(u.created_at).toLocaleDateString("ru-RU")}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2 text-xs"
                          onClick={() => openEditDialog(u)}
                        >
                          Изменить
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 px-2 text-xs"
                          onClick={() => openResetDialog(u)}
                        >
                          <KeyRound className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Edit dialog */}
      <Dialog open={!!editTarget} onOpenChange={(open) => !open && setEditTarget(null)}>
        <DialogContent>
          <form onSubmit={handleEditSubmit}>
            <DialogHeader>
              <DialogTitle>Редактировать пользователя</DialogTitle>
              <DialogDescription>
                @{editTarget?.username}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="edit-fullname">Полное имя</Label>
                <Input
                  id="edit-fullname"
                  value={editFullName}
                  onChange={(e) => setEditFullName(e.target.value)}
                />
              </div>
              <div className="grid gap-2">
                <Label>Роль</Label>
                <Select
                  value={editRole}
                  onValueChange={(v) => setEditRole(v as typeof editRole)}
                >
                  <SelectTrigger disabled={editTarget?.user_id === currentUserId}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="admin">Администратор</SelectItem>
                    <SelectItem value="operator">Оператор</SelectItem>
                    <SelectItem value="viewer">Наблюдатель</SelectItem>
                  </SelectContent>
                </Select>
                {editTarget?.user_id === currentUserId && (
                  <p className="text-[10px] text-muted-foreground">
                    Нельзя изменить свою роль.
                  </p>
                )}
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" type="button" onClick={() => setEditTarget(null)}>
                Отмена
              </Button>
              <Button type="submit" disabled={updateMutation.isPending}>
                {updateMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Сохранить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Reset password dialog */}
      <AlertDialog open={!!resetTarget} onOpenChange={(open) => !open && setResetTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Сбросить пароль?</AlertDialogTitle>
            <AlertDialogDescription>
              Пользователь{" "}
              <span className="font-medium text-foreground">
                {resetTarget?.full_name || resetTarget?.username}
              </span>{" "}
              будет обязан установить новый пароль при следующем входе.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="px-6 pb-2">
            <Label htmlFor="reset-pw">Новый временный пароль</Label>
            <div className="mt-1.5 flex gap-2">
              <Input
                id="reset-pw"
                type="text"
                value={resetPassword}
                onChange={(e) => setResetPassword(e.target.value)}
                autoComplete="off"
              />
              <Button
                variant="outline"
                size="sm"
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(resetPassword);
                  toast.success("Скопировано");
                }}
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              disabled={!resetPassword || resetPassword.length < 6 || resetPasswordMutation.isPending}
              onClick={() => {
                if (resetTarget) {
                  resetPasswordMutation.mutate({
                    userId: resetTarget.user_id,
                    password: resetPassword,
                  });
                }
              }}
            >
              Сбросить пароль
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Deactivate confirmation */}
      <AlertDialog
        open={!!deactivateTarget}
        onOpenChange={(open) => !open && setDeactivateTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Отключить пользователя?</AlertDialogTitle>
            <AlertDialogDescription>
              Пользователь{" "}
              <span className="font-medium text-foreground">
                {deactivateTarget?.full_name || deactivateTarget?.username}
              </span>{" "}
              не сможет войти в систему до повторной активации.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Отмена</AlertDialogCancel>
            <AlertDialogAction
              className="bg-orange-600 hover:bg-orange-700 text-white"
              onClick={() => {
                if (deactivateTarget) {
                  updateMutation.mutate({
                    userId: deactivateTarget.user_id,
                    is_active: false,
                  });
                  setDeactivateTarget(null);
                }
              }}
            >
              Отключить
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
