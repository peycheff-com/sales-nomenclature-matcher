import * as React from "react"
import { Check, ChevronsUpDown } from "lucide-react"

import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"

export interface ModelOption {
  id: string;
  name: string;
  context_length: number;
}

interface ModelComboboxProps {
  value: string;
  onChange: (value: string) => void;
  options?: ModelOption[];
  isLoading?: boolean;
  placeholder?: string;
}

export function ModelCombobox({
  value,
  onChange,
  options = [],
  isLoading,
  placeholder = "Выберите модель...",
}: ModelComboboxProps) {
  const [open, setOpen] = React.useState(false)
  const [search, setSearch] = React.useState("")

  const displayValue = React.useMemo(() => {
    if (!value) return placeholder
    const found = options.find((opt) => opt.id === value)
    return found ? found.name : value
  }, [value, options, placeholder])

  const showCustomOption = search.length > 0 && !options.find((opt) => opt.id === search)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger render={<Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between"
        />}>
          <span className="truncate">{displayValue}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
      </PopoverTrigger>
      <PopoverContent className="w-[400px] p-0" align="start">
        <Command>
          <CommandInput 
            placeholder="Поиск модели..." 
            value={search} 
            onValueChange={setSearch} 
          />
          <CommandList>
            <CommandEmpty>
              {isLoading ? "Загрузка моделей..." : "Модели не найдены."}
              {search && (
                <Button 
                  variant="link" 
                  className="mt-2 text-primary"
                  onClick={() => {
                    onChange(search)
                    setOpen(false)
                    setSearch("")
                  }}
                >
                  Использовать "{search}"
                </Button>
              )}
            </CommandEmpty>
            <CommandGroup>
              {options.map((option) => (
                <CommandItem
                  key={option.id}
                  value={option.id + " " + option.name} // Include id and name for search
                  onSelect={() => {
                    onChange(option.id)
                    setOpen(false)
                    setSearch("")
                  }}
                >
                  <Check
                    className={cn(
                      "mr-2 h-4 w-4",
                      value === option.id ? "opacity-100" : "opacity-0"
                    )}
                  />
                  <span>{option.name}</span>
                  <span className="ml-2 text-xs text-muted-foreground truncate max-w-[120px]">
                    ({option.id})
                  </span>
                </CommandItem>
              ))}
              {showCustomOption && (
                <CommandItem
                  value={search}
                  onSelect={() => {
                    onChange(search)
                    setOpen(false)
                    setSearch("")
                  }}
                >
                  <Check className="mr-2 h-4 w-4 opacity-0" />
                  <span className="font-medium text-primary">Использовать "{search}"</span>
                </CommandItem>
              )}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}
