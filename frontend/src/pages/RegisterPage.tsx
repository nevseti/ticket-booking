import { Alert, Anchor, Button, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { useForm } from '@mantine/form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'

import { useRegister } from '../api/generated/identity/identity'
import { safeNext } from '../features/auth/safeNext'
import { serverFieldErrors } from '../features/forms/serverErrors'
import { useCurrentUser, useSetCurrentUser } from '../features/auth/useCurrentUser'

export function RegisterPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const { user } = useCurrentUser()
  const setCurrentUser = useSetCurrentUser()
  const register = useRegister()

  const form = useForm({
    initialValues: { name: '', email: '', password: '', confirm: '' },
    validate: {
      name: (v) => (v.trim() ? null : 'Введите имя'),
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : 'Введите email'),
      password: (v) => (v.length >= 8 ? null : 'Минимум 8 символов'),
      confirm: (v, values) => (v === values.password ? null : 'Пароли не совпадают'),
    },
  })

  if (user) return <Navigate to={next} replace />

  const submit = form.onSubmit(async ({ name, email, password }) => {
    try {
      const me = await register.mutateAsync({ data: { name, email, password } })
      setCurrentUser(me)
      navigate(next, { replace: true })
    } catch (error) {
      // Ошибки валидации — у полей формы, остальные — в общем блоке над формой.
      form.setErrors(serverFieldErrors(error))
    }
  })

  const emailTaken = register.error?.code === 'EMAIL_TAKEN'

  return (
    <Stack maw={420} mx="auto" py="xl">
      <Title order={2}>Регистрация</Title>
      <Paper withBorder p="lg">
        <form onSubmit={submit}>
          <Stack>
            {register.error && !emailTaken && register.error.code !== 'VALIDATION_ERROR' && (
              <Alert color="red" variant="light">
                {register.error.message}
              </Alert>
            )}
            <TextInput label="Имя" autoComplete="name" {...form.getInputProps('name')} />
            <TextInput
              label="Email"
              autoComplete="email"
              {...form.getInputProps('email')}
              error={form.errors.email ?? (emailTaken ? register.error?.message : undefined)}
            />
            <PasswordInput
              label="Пароль"
              description="Не короче 8 символов"
              autoComplete="new-password"
              {...form.getInputProps('password')}
            />
            <PasswordInput
              label="Пароль ещё раз"
              autoComplete="new-password"
              {...form.getInputProps('confirm')}
            />
            <Button type="submit" loading={register.isPending}>
              Создать аккаунт
            </Button>
          </Stack>
        </form>
      </Paper>
      <Text size="sm" ta="center">
        Уже есть аккаунт?{' '}
        <Anchor component={Link} to={`/login?next=${encodeURIComponent(next)}`}>
          Войти
        </Anchor>
      </Text>
    </Stack>
  )
}
