import { Alert, Anchor, Button, Paper, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core'
import { useForm } from '@mantine/form'
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router'

import { useLogin } from '../api/generated/identity/identity'
import { safeNext } from '../features/auth/safeNext'
import { serverFieldErrors } from '../features/forms/serverErrors'
import { useCurrentUser, useSetCurrentUser } from '../features/auth/useCurrentUser'

export function LoginPage() {
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const navigate = useNavigate()
  const { user } = useCurrentUser()
  const setCurrentUser = useSetCurrentUser()
  const login = useLogin()

  const form = useForm({
    initialValues: { email: '', password: '' },
    validate: {
      email: (v) => (/^\S+@\S+\.\S+$/.test(v) ? null : 'Введите email'),
      password: (v) => (v ? null : 'Введите пароль'),
    },
  })

  if (user) return <Navigate to={next} replace />

  const submit = form.onSubmit(async (values) => {
    try {
      const me = await login.mutateAsync({ data: values })
      setCurrentUser(me)
      navigate(next, { replace: true })
    } catch (error) {
      // Ошибки валидации — у полей формы, остальные — в общем блоке над формой.
      form.setErrors(serverFieldErrors(error))
    }
  })

  return (
    <Stack maw={420} mx="auto" py="xl">
      <Title order={2}>Вход</Title>
      <Paper withBorder p="lg">
        <form onSubmit={submit}>
          <Stack>
            {login.error && login.error.code !== 'VALIDATION_ERROR' && (
              <Alert color="red" variant="light">
                {login.error.message}
              </Alert>
            )}
            <TextInput label="Email" autoComplete="email" {...form.getInputProps('email')} />
            <PasswordInput
              label="Пароль"
              autoComplete="current-password"
              {...form.getInputProps('password')}
            />
            <Button type="submit" loading={login.isPending}>
              Войти
            </Button>
          </Stack>
        </form>
      </Paper>
      <Text size="sm" ta="center">
        Нет аккаунта?{' '}
        <Anchor component={Link} to={`/register?next=${encodeURIComponent(next)}`}>
          Зарегистрироваться
        </Anchor>
      </Text>
    </Stack>
  )
}
