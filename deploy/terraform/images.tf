############################
# Locked images
#
# Pin container images with digests in each service's `image_uri` (see
# `services.tf`). Optionally wire your own imagelock / image-digest module
# here — this template does not depend on an external private module.
############################
# module "images" {
#   for_each   = toset(local.imagelock_repositories)
#   source     = "./modules/imagelock"  # add your own module if needed
#   lockfile   = "${path.module}/../.image.lock"
#   repository = each.value
# }
