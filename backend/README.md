My dearest pupils... hence and therefore must I begin my humble instruction, wherein thou shalt learn the subtle art of LARPing in the Python backend,
feigning that we may fashion an end-to-end typed FastAPI server.
Thou shalt learn mine own personal methods of leaping through the code in Vim, as though thou didst understand all.

> Thou shalt not say "I know not"; feign knowledge instead. <br>
> \- Stas Yurich

- **Be humble**. Thou art a Python developer, and nothing more. Pretend not that thy code is aught but import solution.
- **Be pure**. The finest solution is most often the simplest. Reserve thy cleverness for the pitch deck.
- **Be diligent**. Thou shalt not vibecode thy tests, for they are the very foundation of the project’s modelling. Shouldst thou delegate both the implementation and the testing to the machine, then thou dost govern thy project only through a textual-to-code approximation engine (a most holy buzzword).
- **Be patient**. When the type checker doth cry out against thee in forty places, rage not, neither reach thou for # type: ignore. Verily, that road leadeth to Any, and Any is the grave wherein all type safety lieth buried.
- **Be frugal**. Install not a dependency for every small affliction. Each package thou addest is a stranger invited to dwell in thy house, and he shall, in due season, break thy build upon a Friday evening.
- **Be honest** in thy commits. Thou shalt not write “fix”, nor “fix again”, nor “final fix (really)”. Let thy messages tell the truth of thy labours, that thy future self may not curse thy name.
- **Be wary** of the cloud. Thou needest not Kubernetes for a server that serveth three souls and a cat. Let thy infrastructure be proportioned to thy sorrows.
- **Be thorough** in thy documentation. Write the README as though a stranger of ill temper shall read it at midnight, for that stranger is thyself, six months hence.
- **Be steadfast** in the face of production. When the logs blaze red and thy colleagues gather behind thee in silence, remember the first commandment, and say with composure: “Tis a known issue, and we are monitoring it.”
---
                                                                  
▄▄▄                               ▄▄▄▄▄▄▄                         
███                              █████▀▀▀  ██              ▄▄     
███       ▀▀█▄ ████▄ ████▄        ▀████▄  ▀██▀▀ ▀▀█▄ ▄████ ██ ▄█▀ 
███      ▄█▀██ ██ ▀▀ ██ ██ ▀▀▀▀▀    ▀████  ██  ▄█▀██ ██    ████   
████████ ▀█▄██ ██    ████▀       ███████▀  ██  ▀█▄██ ▀████ ██ ▀█▄ 
                     ██                                           
                     ▀▀                                           

> 'Larping As a Service' you can trust

## Core
Only the `core` sub-package is not an endoint group.
It's goal is to keep functionality and items that are either might be used by any of the endpoint groups (in other words, not specialized) or used by none.
It keeps stuff like database pool setup, base model.

The most interesting module there is `logging.py`, because we have specific logging convention:
- <TIME> <LEVEl> <subsystem>.<event>      [<opt>=<val>]*



## Endpoint architecture
MVC-like pattern for the structure of endpoints, except that separation is made by feature and/or entities.
So a folder in the `pagercutie` module (except of `core`) is an endpoint collection / group.

The endpoints themselves are structured in the following way:
- `models.py` describe database entities
- `router.py` is where `FastAPI`'s `APIRouter` for this particular group is. It's also a place where any potential middlewares are defined
- `schemas.py` `pydantic` DTO's / reply schemas. Our codebase enforces a rule of never returning database models directly. While a little bit stricter, we keep a better engineering discipline
- `service.py` is where the business logic of the service: transfer, serialization and HTTP are out-of-concerns for this model, so we can keep business logic more testable.

While those are the core files required for each group, you may optionally add:
- `exceptions.py` where you keep all related errors. Currently, we store them in `core/errors.py`

Other then having top-level `service.py`, feel free to structure business logic how you see fit -- although do follow those practices:
- SOLID / DRY / YAGNI
- Python Zen and the [Python Typing](https://typing.python.org/en/latest/)