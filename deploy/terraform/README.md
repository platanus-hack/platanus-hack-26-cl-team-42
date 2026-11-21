# Terraform AWS ECS

Esta configuración de Terraform está diseñada para facilitar el despliegue de aplicaciones web dockerizadas en AWS ECS Fargate.

Adopta una estrategia de un Terraform Workspace por cada ambiente, usando una única cuenta AWS, con redes VPC separadas para cada ambiente.

Reconoce recursos compartidos entre ambientes, que son aprovisionados con configuraciones específicas:
  * Pool de usuarios Cognito para autenticación (namespace "core")
  * Zona DNS donde se crean los registros para cada ambiente
  * Credenciales para repositorios de imágenes (GHCR)

## Variables

Esta arquitectura separa en dos capas distintas las variables de "entrada" que permiten la parametrización de la configuración.
Se ofrecen como variables de entrada los parámetros que hacen sentido variar de ambiente en ambiente y/o que son sensibles y no apropiados para versionar.

A partir de las variables de entrada, se construyen variables locales con nombres claros que se utilizan en la configuración.
La configuración por defecto evita utilizar las variables de entrada (`var.*`) como parámetro directo para la configuración de recursos, prefiriendo en cambio
construir variables locales (`local.*`) para este efecto. Esto facilita el proceso de variar el esquema de variables que se presenta a los operadores, sin exponer
detalles de la implementación del diseño de módulos. Facilita y promueve también mantener un diseño organizado de variables locales para definir parámetros de 
configuración de recursos que son deseables mantener versionados formalmente en la configuración de la arquitectura (y no como valores "volátiles").

### Proyecto

El archivo `project.tf` en particular contiene variables locales que describen servicios externos y otras configuraciones y parámetros específicos del proyecto.

## Archivos de Configuración

El archivo `main.tf` no se genera por la arquitectura base webapp y se reserva como punto de partida para la configuración específica del proyecto.

Los siguientes archivos se entregan pre-configurados por la arquitectura base:

  * `provider.tf` - Configuración de proveedores (AWS, Sentry)
  * `variables.tf` - Definición de variables de entrada
  * `project.tf` - Variables locales del proyecto
  * `outputs.tf` - Definición de outputs
  * `webapp.tf` - Configuración de recursos base (VPC, Cluster, DB, Ingress, Auth, Storage)
  * `services.tf` - Configuración de servicios ECS
  * `sentry.tf` - Configuración de variables de entorno de Sentry
  * `images.tf` - Stub opcional para pinning de imágenes Docker

Para facilitar el mantenimiento, se recomienda **NO EDITAR `webapp.tf`** salvo ajustes de configuraciones de los módulos webapp ahí utilizados; pero siempre evitando desarrollar
detalles del proyecto. Para configuración específica del proyecto, utilizar `main.tf`, `services.tf` u otros archivos nuevos.

## Módulos

### Módulos de Usuario [./modules]
La ruta clásica de `modules` se entrega vacía por parte de la arquitectura base webapp y es el lugar ideal para desarrollar módulos específicos del proyecto, pues las
actualizaciones nunca los sobreescribirán.

### Módulos Webapp [./webapp]

Estos módulos son provistos directamente por la arquitectura base webapp y se recomienda no modificarlos para facilitar las actualizaciones en el proyecto.

#### **[./webapp/auth](./webapp/auth)** - Autenticación Cognito
  - Crea AWS Cognito User Pool para gestión de usuarios
  - Configura dominio personalizado para el User Pool
  - Cliente OAuth para integración con ALB
  - Templates de email personalizados (verificación e invitación)

#### **[./webapp/network](./webapp/network)** - Red VPC
  - Crea VPC dedicada al entorno con CIDR configurable
  - Subredes públicas (para ALB y NAT Gateway)
  - Subredes privadas (para servicios ECS y RDS)
  - Internet Gateway y NAT Gateway
  - Tablas de ruteo configuradas

#### **[./webapp/cluster](./webapp/cluster)** - Cluster ECS
  - Cluster ECS Fargate para contenedores
  - Service Discovery para comunicación entre servicios
  - Rol de ejecución para tareas ECS
  - Permisos para acceso a secretos y logs
  - CloudWatch Log Groups

#### **[./webapp/cluster-service](./webapp/cluster-service)** - Servicio ECS
  - Módulo reutilizable para crear servicios en el cluster
  - Definición de tareas ECS con Fargate
  - Target Group para el ALB
  - Security Groups configurados
  - Integración con Service Connect
  - Soporte para múltiples contenedores

#### **[./webapp/ingress](./webapp/ingress)** - Balanceador de Carga
  - Application Load Balancer (ALB)
  - Certificados TLS con ACM
  - Listeners HTTP (redirección) y HTTPS
  - Reglas de ruteo configurables por path
  - Integración con Cognito para autenticación
  - Security Groups para tráfico web

#### **[./webapp/db](./webapp/db)** - Base de Datos
  - Aurora PostgreSQL Serverless v2
  - Subnet group para alta disponibilidad
  - Security Groups con acceso controlado
  - Credenciales en AWS Secrets Manager
  - Políticas IAM para RDS Data API
  - Escalado automático configurado

#### **[./webapp/storage](./webapp/storage)** - Almacenamiento
  - Bucket S3 para archivos media
  - Políticas IAM para acceso desde ECS
  - Configuración de permisos granulares

#### **[./webapp/twingate](./webapp/twingate)** - Acceso Remoto (Opcional)
  - Remote Network en Twingate
  - Connector desplegado en ECS
  - Configuración de tokens
  - Acceso seguro a recursos privados

## Servicios

La configuración de servicios se realiza en `services.tf`. Por defecto incluye un servicio de ejemplo (`httpbin`) que puedes reemplazar con tus propios servicios.

Para agregar un nuevo servicio:

1. Declara el módulo en `services.tf`:
```hcl
module "service-mi-app" {
  source = "./webapp/cluster-service"
  
  namespace = local.project.namespace
  name      = "mi-app"
  image_uri = "mi-registry/mi-app:latest"
  
  base_container_definition = {
    environment = [
      { name = "DATABASE_URL", value = module.db.database_url },
      { name = "MEDIA_BUCKET_NAME", value = module.media.bucket_name },
    ]
  }
  
  task_role_policy_arns = {
    media_access = module.media.access_policy_arn
  }
  
  subnet_ids = module.network.private_subnet_ids
}
```

2. Si necesita acceso a la base de datos, agrégalo a `services_with_db_access` en `services.tf`

## Image digests

Pin container images with digests (or immutable tags) in each service's
`image_uri` in `services.tf`. An optional `images.tf` stub is left for you to
wire your own imagelock / digest-locking module if you want one.