import React from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';

type FieldType = 'text' | 'password' | 'select';

export interface FieldOption {
  label: string;
  value: string;
}

export interface FieldConfig {
  name: string;
  label: string;
  placeholder?: string;
  description?: string;
  type: FieldType;
  options?: FieldOption[]; // for select
  required?: boolean;
}

export interface ConnectorFormProps {
  title: string;
  description?: string;
  fields: FieldConfig[];
  onSubmit: (values: Record<string, string>) => Promise<void> | void;
  submitLabel?: string;
}

const ConnectorForm: React.FC<ConnectorFormProps> = ({ title, description, fields, onSubmit, submitLabel }) => {
  const schemaShape: Record<string, z.ZodTypeAny> = {};
  fields.forEach((f) => {
    const base = z.string().trim();
    schemaShape[f.name] = f.required ? base.min(1, `${f.label} is required`) : base.optional();
  });
  const schema = z.object(schemaShape);

  const form = useForm<Record<string, string>>({
    resolver: zodResolver(schema),
    defaultValues: fields.reduce((acc, f) => ({ ...acc, [f.name]: '' }), {} as Record<string, string>),
  });

  const handleSubmit = async (values: Record<string, string>) => {
    await onSubmit(values);
  };

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-xl font-semibold">{title}</h2>
        {description && <p className="text-sm text-muted-foreground">{description}</p>}
      </div>
      <Form {...form}>
        <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
          {fields.map((field) => (
            <FormField
              key={field.name}
              control={form.control}
              name={field.name as any}
              render={({ field: rhfField }) => (
                <FormItem>
                  <FormLabel>{field.label}</FormLabel>
                  <FormControl>
                    {field.type === 'select' ? (
                      <Select value={rhfField.value} onValueChange={rhfField.onChange}>
                        <SelectTrigger>
                          <SelectValue placeholder={field.placeholder || 'Select'} />
                        </SelectTrigger>
                        <SelectContent>
                          {(field.options || []).map((opt) => (
                            <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    ) : (
                      <Input
                        type={field.type === 'password' ? 'password' : 'text'}
                        placeholder={field.placeholder}
                        {...rhfField}
                      />
                    )}
                  </FormControl>
                  {field.description && <FormDescription>{field.description}</FormDescription>}
                  <FormMessage />
                </FormItem>
              )}
            />
          ))}
          <div className="pt-2">
            <Button type="submit">{submitLabel || 'Connect'}</Button>
          </div>
        </form>
      </Form>
    </div>
  );
};

export default ConnectorForm;