import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  listUsers,
  createUser,
  updateUser,
  resetUserPassword,
  type UserDetail,
} from "@/api/users";
import { PageLayout } from "@/components/layout/page-layout";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, KeyRound } from "lucide-react";

const ROLES = ["admin", "operator", "viewer", "reviewer", "catalog_operator"] as const;

const ROLE_LABELS: Record<string, string> = {
  admin: "Админ",
  operator: "Оператор",
  viewer: "Наблюдатель",
  reviewer: "Ревьюер",
  catalog_operator: "Каталог-оператор",
};

export default function UsersPage() {
  const queryClient = useQueryClient();

  const [createOpen, setCreateOpen] = useState(false);
  const [editUser, setEditUser] = useState<UserDetail | null>(null);
  const [resetUser, setResetUser] = useState<UserDetail | null>(null);

  // Create form state
  const [createForm, setCreateForm] = useState({
    username: "",
    password: "",
    full_name: "",
    role: "operator" as string,
  });

  // Edit form state
  const [editForm, setEditForm] = useState({
    full_name: "",
    role: "",
    is_active: true,
  });

  // Reset password state
  const [newPassword, setNewPassword] = useState("");

  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const createMutation = useMutation({
    mutationFn: (data: typeof createForm) => createUser(data as Parameters<typeof createUser>[0]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setCreateOpen(false);
      setCreateForm({ username: "", password: "", full_name: "", role: "operator" });
      toast.success("Пользователь создан");
    },
    onError: () => toast.error("Ошибка при создании пользователя"),
  });

  const updateMutation = useMutation({
    mutationFn: (data: { id: string; payload: typeof editForm }) =>
      updateUser(data.id, data.payload as Parameters<typeof updateUser>[1]),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEditUser(null);
      toast.success("Пользователь обновлён");
    },
    onError: () => toast.error("Ошибка при обновлении пользователя"),
  });

  const resetMutation = useMutation({
    mutationFn: (data: { id: string; password: string }) =>
      resetUserPassword(data.id, data.password),
    onSuccess: () => {
      setResetUser(null);
      setNewPassword("");
      toast.success("Пароль сброшен");
    },
    onError: () => toast.error("Ошибка при сбросе пароля"),
  });

  function openEdit(user: UserDetail) {
    setEditForm({
      full_name: user.full_name ?? "",
      role: user.role,
      is_active: user.is_active,
    });
    setEditUser(user);
  }

  function openReset(e: React.MouseEvent, user: UserDetail) {
    e.stopPropagation();
    setNewPassword("");
    setResetUser(user);
  }

  const users = usersQuery.data?.items ?? [];

  return (
    <PageLayout title="Пользователи">
      <div className="flex justify-end mb-4">
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4 mr-2" />
          Создать
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Логин</TableHead>
              <TableHead>Полное имя</TableHead>
              <TableHead>Роль</TableHead>
              <TableHead>Активен</TableHead>
              <TableHead>Создан</TableHead>
              <TableHead className="w-[100px]" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {users.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  {usersQuery.isLoading ? "Загрузка..." : "Нет пользователей"}
                </TableCell>
              </TableRow>
            )}
            {users.map((user) => (
              <TableRow
                key={user.user_id}
                className="cursor-pointer"
                onClick={() => openEdit(user)}
              >
                <TableCell className="font-medium">{user.username}</TableCell>
                <TableCell>{user.full_name ?? "—"}</TableCell>
                <TableCell>
                  <Badge variant="outline">
                    {ROLE_LABELS[user.role] ?? user.role}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={user.is_active ? "default" : "secondary"}>
                    {user.is_active ? "Да" : "Нет"}
                  </Badge>
                </TableCell>
                <TableCell>
                  {new Date(user.created_at).toLocaleDateString("ru-RU")}
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon"
                    title="Сбросить пароль"
                    onClick={(e) => openReset(e, user)}
                  >
                    <KeyRound className="h-4 w-4" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* Create user dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Создать пользователя</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="create-username">Логин</Label>
              <Input
                id="create-username"
                value={createForm.username}
                onChange={(e) =>
                  setCreateForm((f) => ({ ...f, username: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="create-password">Пароль</Label>
              <Input
                id="create-password"
                type="password"
                value={createForm.password}
                onChange={(e) =>
                  setCreateForm((f) => ({ ...f, password: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="create-fullname">Полное имя</Label>
              <Input
                id="create-fullname"
                value={createForm.full_name}
                onChange={(e) =>
                  setCreateForm((f) => ({ ...f, full_name: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label>Роль</Label>
              <Select
                value={createForm.role}
                onValueChange={(v) => setCreateForm((f) => ({ ...f, role: v || "" }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROLE_LABELS[r] ?? r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => createMutation.mutate(createForm)}
              disabled={
                !createForm.username ||
                !createForm.password ||
                createMutation.isPending
              }
            >
              {createMutation.isPending ? "Создание..." : "Создать"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit user dialog */}
      <Dialog open={!!editUser} onOpenChange={(open) => !open && setEditUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Редактирование: {editUser?.username}
            </DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="edit-fullname">Полное имя</Label>
              <Input
                id="edit-fullname"
                value={editForm.full_name}
                onChange={(e) =>
                  setEditForm((f) => ({ ...f, full_name: e.target.value }))
                }
              />
            </div>
            <div className="grid gap-2">
              <Label>Роль</Label>
              <Select
                value={editForm.role}
                onValueChange={(v) => setEditForm((f) => ({ ...f, role: v || "" }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROLE_LABELS[r] ?? r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="edit-active">Активен</Label>
              <Switch
                id="edit-active"
                checked={editForm.is_active}
                onCheckedChange={(checked) =>
                  setEditForm((f) => ({ ...f, is_active: checked }))
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() =>
                editUser &&
                updateMutation.mutate({ id: editUser.user_id, payload: editForm })
              }
              disabled={updateMutation.isPending}
            >
              {updateMutation.isPending ? "Сохранение..." : "Сохранить"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset password dialog */}
      <Dialog open={!!resetUser} onOpenChange={(open) => !open && setResetUser(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Сбросить пароль: {resetUser?.username}
            </DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="new-password">Новый пароль</Label>
              <Input
                id="new-password"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() =>
                resetUser &&
                resetMutation.mutate({
                  id: resetUser.user_id,
                  password: newPassword,
                })
              }
              disabled={!newPassword || resetMutation.isPending}
            >
              {resetMutation.isPending ? "Сброс..." : "Сбросить пароль"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageLayout>
  );
}
